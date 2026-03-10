"""SISBOM GraphQL client."""

from __future__ import annotations

import json
from contextlib import contextmanager
from typing import Any

import httpx

from .auth import get_credentials, load_token, save_token
from .config import API_BG, API_URL, STORAGE_URL

# GraphQL error messages that indicate an auth/token problem
_AUTH_ERROR_KEYWORDS = (
    "not authenticated",
    "unauthorized",
    "jwt expired",
    "invalid token",
    "token inválido",
    "não autenticado",
    "unauthenticated",
    "authentication",
)


class SISBOMClient:
    """HTTP client for the SISBOM GraphQL API."""

    def __init__(self, api_url: str | None = None) -> None:
        self._api_url = api_url or API_URL
        self._token: str | None = None
        self._in_auth_flow: bool = False  # guard against recursive _ensure_auth
        self._http = httpx.Client(
            timeout=30,
            follow_redirects=True,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "SISBOMClient":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    # --- Auth helpers ---

    def _ensure_auth(self) -> None:
        """Garante que há token válido. Tenta cache, depois login fresh.

        Protegido contra recursão: não faz nada se já estiver num fluxo de login.
        """
        if self._in_auth_flow:
            return
        if self._token:
            return
        # Tenta carregar do disco
        cached = load_token()
        if cached:
            self._token = cached
            return
        # Login fresh
        result = self.login()
        if not result.get("ok"):
            raise RuntimeError("Auto-login falhou — verifique credenciais no Bitwarden")

    @contextmanager
    def batch_mode(self):
        """Login uma vez, reutiliza token pra N operações.

        Usage::

            with client.batch_mode():
                for m in militares:
                    client.some_query(m)
        """
        self._ensure_auth()
        yield self

    # --- Auth ---

    def login(self, cpf: str | None = None, password: str | None = None) -> dict:
        """Authenticate and obtain JWT token.

        If cpf/password not provided, reads from Bitwarden vault.
        Returns user info dict.
        """
        # Try cached token first — trust time-based validation from load_token().
        # Skipping me() round-trip here: saves ~800ms and avoids a recursion risk
        # where _gql_raw() retry → login() → me() → _gql_raw() retry → login() ...
        # If the cached token is actually server-rejected, the next API call will
        # trigger the retry/re-login path in _gql_raw() automatically.
        cached = load_token()
        if cached:
            self._token = cached
            return {"ok": True, "cached": True}

        if not cpf or not password:
            cpf, password = get_credentials()

        # Step 1: seiLogin mutation — marcar _in_auth_flow para evitar recursão em _ensure_auth
        self._in_auth_flow = True
        try:
            result = self._gql(
                """mutation seiLogin($str_cpf: String, $password: String){
                    seiLogin(str_cpf: $str_cpf, password: $password){
                        forca_id
                        token
                    }
                }""",
                variables={"str_cpf": cpf, "password": password},
            )
        finally:
            self._in_auth_flow = False

        sei_login = result.get("seiLogin")
        if not sei_login or not sei_login.get("token"):
            return {"ok": False, "message": "Login falhou — verifique CPF/senha"}

        self._token = sei_login["token"]
        save_token(self._token)

        return {"ok": True, "token_preview": self._token[:20] + "...", "forca_id": sei_login["forca_id"]}

    def me(self) -> dict | None:
        """Get current user info."""
        result = self._gql(
            """query me {
                me {
                    _id
                    str_cpf
                }
            }"""
        )
        return result.get("me")

    # --- Efetivo ---

    def militares(
        self,
        *,
        active: bool = True,
        lotacao: str | None = None,
        fields: str | None = None,
    ) -> list[dict]:
        """List militares.

        Args:
            active: Filter by active status.
            lotacao: Filter by lotação ID.
            fields: GraphQL fields to return (default: basic info).
        """
        if not fields:
            fields = """
                _id
                forca_id
                str_nomecurto
                str_nomeguerra
                str_matricula
                str_cpf
                _patente
                str_quadro
                _lotacao
                lotacao { N1 N2 N3 }
                dt_incorporacao
                index
                active
                situacao_status
                comportamento
                pessoa {
                    str_nome
                    str_sexo
                    dt_nascimento
                    str_telefone
                    str_telefonecelular
                    str_email
                    str_tipo_sanguineo
                    str_escolaridade
                }
            """

        variables: dict[str, Any] = {"active": active}
        if lotacao:
            variables["lotacao"] = lotacao

        result = self._gql(
            f"""query militares($active: Boolean, $forca_id: String, $lotacao: String){{
                militares(active: $active, forca_id: $forca_id, lotacao: $lotacao){{
                    {fields}
                }}
            }}""",
            variables=variables,
        )
        return result.get("militares", [])

    def militar(
        self,
        *,
        _id: str | None = None,
        matricula: str | None = None,
        cpf: str | None = None,
        fields: str | None = None,
    ) -> dict | None:
        """Get a single militar's info.

        Args:
            _id: Internal ID.
            matricula: Matrícula number.
            cpf: CPF number.
            fields: GraphQL fields to return.
        """
        if not fields:
            fields = """
                _id
                forca_id
                str_nomecurto
                str_nomeguerra
                str_matricula
                str_cpf
                _patente
                str_quadro
                _lotacao
                lotacao { N1 N2 N3 }
                dt_incorporacao
            """

        variables: dict[str, Any] = {}
        if _id:
            variables["_id"] = _id
        if matricula:
            variables["str_matricula"] = matricula
        if cpf:
            variables["str_cpf"] = cpf

        result = self._gql(
            f"""query militar($_id: ID, $str_matricula: String, $str_cpf: String){{
                militar(_id: $_id, str_matricula: $str_matricula, str_cpf: $str_cpf){{
                    {fields}
                }}
            }}""",
            variables=variables,
        )
        return result.get("militar")

    def efetivo(self, fields: str | None = None) -> list[dict]:
        """Get full efetivo list (cached in API).

        Note: MilitarEfetivo has different field types than 'militares' query.
        _patente is Int (not object), lotacao uses LotacaoNiveis (N1/N2/N3).
        """
        if not fields:
            fields = """
                _id
                forca_id
                str_nomecurto
                str_matricula
                _patente
                index
                lotacao { N1 N2 N3 }
            """

        result = self._gql(
            f"""query MilitarEfetivo {{
                MilitarEfetivo {{
                    {fields}
                }}
            }}"""
        )
        return result.get("MilitarEfetivo", [])

    def aniversariantes(self, ano: str, mes: str, dia: str | None = None) -> list[dict]:
        """Get militares by birth date."""
        variables: dict[str, Any] = {"ano": ano, "mes": mes}
        if dia:
            variables["dia"] = dia

        result = self._gql(
            """query dt_nascimento($ano: String, $mes: String, $dia: String){
                dt_nascimento(ano: $ano, mes: $mes, dia: $dia){
                    _id
                    str_nomecurto
                    str_matricula
                    _patente
                    _lotacao
                    lotacao { N1 N2 N3 }
                    pessoa { dt_nascimento str_telefonecelular }
                }
            }""",
            variables=variables,
        )
        return result.get("dt_nascimento", [])

    # --- Diárias ---

    def diarias(self, fields: str | None = None) -> list[dict]:
        """List diárias.

        MilitarDiaria type: _id, _lotacao, date, executor{Militar},
        escalado{Militar}, atividade, dt_inicio_date, dt_inicio_time,
        dt_fim_date, dt_fim_time.
        """
        if not fields:
            fields = """
                _id
                _lotacao
                date
                atividade
                atividade_extra
                dt_inicio_date
                dt_inicio_time
                dt_fim_date
                dt_fim_time
                executor { str_nomecurto str_matricula _patente }
                escalado  { str_nomecurto str_matricula _patente }
            """

        result = self._gql(
            f"""query MilitarDiarias {{
                MilitarDiarias {{
                    {fields}
                }}
            }}"""
        )
        return result.get("MilitarDiarias", [])

    # --- Lotações ---

    def lotacoes(self) -> list[dict]:
        """List all lotações (units)."""
        result = self._gql(
            """query Lotacoes {
                Lotacoes {
                    _id
                    str_sigla
                    str_sigla_extenso
                    str_nome
                    nivel
                    operacional
                }
            }"""
        )
        return result.get("Lotacoes", [])

    # --- Guarnições ---

    def guarnicoes(self, fields: str | None = None) -> list[dict]:
        """List guarnições."""
        if not fields:
            fields = """
                _id
                dt_servico
                str_tipo
                _lotacao { str_lotacao }
            """

        result = self._gql(
            f"""query MapaGuarnicoes {{
                MapaGuarnicoes {{
                    {fields}
                }}
            }}"""
        )
        return result.get("MapaGuarnicoes", [])

    # --- Férias ---

    def ferias_lotacao(self, fields: str | None = None) -> list[dict]:
        """List férias by lotação."""
        if not fields:
            fields = """
                _id
                _militar { str_nomecurto str_matricula }
                dt_inicio
                dt_fim
                str_status
            """

        result = self._gql(
            f"""query FeriasLotacao {{
                FeriasLotacao {{
                    {fields}
                }}
            }}"""
        )
        return result.get("FeriasLotacao", [])

    # --- Permutas ---

    def permutas(self, fields: str | None = None) -> list[dict]:
        """List permutas."""
        if not fields:
            fields = """
                _id
                _militar { str_nomecurto }
                _militar_permuta { str_nomecurto }
                dt_servico
                str_status
            """

        result = self._gql(
            f"""query MilitarPermutas {{
                MilitarPermutas {{
                    {fields}
                }}
            }}"""
        )
        return result.get("MilitarPermutas", [])

    # --- Frotas ---

    def viaturas(self, fields: str | None = None) -> list[dict]:
        """List viaturas."""
        if not fields:
            fields = """
                _id
                prefixo
                placa
                modelo
                marca
                tipo_viatura
                operante
                ativo
                cond_nomecurto
            """

        result = self._gql(
            f"""query FrotasViaturas {{
                FrotasViaturas {{
                    {fields}
                }}
            }}"""
        )
        return result.get("FrotasViaturas", [])

    # --- Mapa de Força ---

    def mapa_forca_militares(self, date: str, lotacao: str) -> list[dict]:
        """List militares on the force map for a given date/lotação.

        Args:
            date: Date string (YYYY-MM-DD).
            lotacao: Lotação code (e.g. PABM_3GBM_APODI).

        Returns:
            List of MilitarMapa dicts with bo_diaria (DO checkbox).
        """
        result = self._gql(
            """query MilitaresMapaForca($date: String, $_lotacao: String) {
                MilitaresMapaForca(date: $date, _lotacao: $_lotacao) {
                    _id
                    str_nomecurto
                    str_matricula
                    bo_diaria
                    atividade
                    _lotacao
                    index
                    _patente
                    updated_at
                }
            }""",
            variables={"date": date, "_lotacao": lotacao},
        )
        mils = result.get("MilitaresMapaForca", [])
        # API ignores _lotacao filter — filter client-side
        if lotacao:
            mils = [m for m in mils if m.get("_lotacao") == lotacao]
        return mils

    def mapa_forca_guarnicoes(self, date: str | None = None, lotacao: str | None = None) -> list[dict]:
        """List guarnições with full garrison composition.

        Uses MapaGuarnicoesMilitar (date-filtered server-side).
        Filters by lotacao client-side.
        """
        variables: dict[str, Any] = {}
        if date:
            variables["date"] = date

        result = self._gql(
            """query MapaGuarnicoesMilitar($date: String) {
                MapaGuarnicoesMilitar(date: $date) {
                    _id
                    date
                    _lotacao
                    atividade
                    atividade_extra
                    _viatura
                    prefixo
                    bf_cmt
                    bo_cad
                    str_alteracoes
                    str_alteracoes_vtr
                    guarnicao {
                        _id
                        bo_ativo
                        bo_diaria
                        index
                        str_funcao
                        str_matricula
                        str_nomecurto
                        str_cpf
                    }
                }
            }""",
            variables=variables if variables else None,
        )
        gus = result.get("MapaGuarnicoesMilitar", [])
        if lotacao:
            gus = [g for g in gus if g.get("_lotacao") == lotacao]
        if date:
            gus = [g for g in gus if g.get("date") == date]
        return gus

    def mapa_forca_viaturas(self, lotacao: str, data: str) -> list[dict]:
        """List viaturas available on the force map.

        Args:
            lotacao: Lotação code.
            data: Date string (YYYY-MM-DD).
        """
        result = self._gql(
            """query FrotasViaturasMapaForca($lotacao: String, $data: String) {
                FrotasViaturasMapaForca(lotacao: $lotacao, data: $data) {
                    _id
                    prefixo
                    placa
                    modelo
                }
            }""",
            variables={"lotacao": lotacao, "data": data},
        )
        return result.get("FrotasViaturasMapaForca", [])

    # --- Ocorrências ---

    def ocorrencias(self, fields: str | None = None) -> list[dict]:
        """List ocorrências."""
        if not fields:
            fields = """
                _id
                str_numero
                dt_ocorrencia
                str_tipo
                str_natureza
                str_endereco
                _lotacao { str_lotacao }
            """

        result = self._gql(
            f"""query Ocorrencias {{
                Ocorrencias {{
                    {fields}
                }}
            }}"""
        )
        return result.get("Ocorrencias", [])

    # --- Licenças ---

    def licencas(self, fields: str | None = None) -> list[dict]:
        """List licenças."""
        if not fields:
            fields = """
                _id
                _militar { str_nomecurto str_matricula }
                str_tipo
                dt_inicio
                dt_fim
                str_status
            """

        result = self._gql(
            f"""query Licencas {{
                Licencas {{
                    {fields}
                }}
            }}"""
        )
        return result.get("Licencas", [])

    # --- Maré (Tides) ---

    def mare(self, location: str = "areia-branca") -> dict:
        """Get tide data from tabuademares.com.

        Args:
            location: Location slug (default: areia-branca for RN coast).
                Other options: natal, macau, mossoro, etc.

        Returns:
            Dict with date, tides (list of {time, type, height}), sun, coef.
        """
        import re

        url = f"https://tabuademares.com/br/rio-grande-do-norte/{location}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        r = self._http.get(url, timeout=15, follow_redirects=True, headers=headers)
        if r.status_code != 200:
            raise RuntimeError(f"Failed to fetch tide data: HTTP {r.status_code}")

        text = r.text
        result: dict[str, Any] = {"location": location, "url": url}

        # Extract date
        date_match = re.search(
            r"HOJE,\s+\w+,\s+(\d+\s+DE\s+\w+\s+DE\s+\d{4})", text
        )
        if date_match:
            result["date"] = date_match.group(1)

        tides: list[dict[str, str]] = []

        # Extract from HTML: spans with class 'rojo' (baixa-mar) and 'azul' (preia-mar)
        # Pattern: <span class='rojo'>baixa-mar</span> foi às <span class='rojo'>0:48</span>
        baixa_matches = re.findall(
            r"<span class=['\"]rojo['\"]>baixa-mar</span>.*?<span class=['\"]rojo['\"]>"
            r"(\d{1,2}:\d{2})</span>",
            text,
        )
        preia_matches = re.findall(
            r"<span class=['\"]azul['\"]>preia-mar</span>.*?<span class=['\"]azul['\"]>"
            r"(\d{1,2}:\d{2})</span>",
            text,
        )

        # Fallback: simpler pattern from the status divs
        if not baixa_matches:
            baixa_matches = re.findall(
                r"<strong>baixa-mar</strong>\s*<br>\s*(\d{1,2}:\d{2})", text
            )
        if not preia_matches:
            preia_matches = re.findall(
                r"<strong>preia-mar</strong>\s*<br>\s*(\d{1,2}:\d{2})", text
            )

        for t in baixa_matches:
            tides.append({"time": t, "type": "baixa-mar"})
        for t in preia_matches:
            tides.append({"time": t, "type": "preia-mar"})

        # Sort by time (padded for correct ordering)
        tides.sort(key=lambda x: x["time"].zfill(5))
        result["tides"] = tides

        # Extract tide heights from narrative:
        # "alturas das marés de hoje são <span class='rojo'>0,8<span ...>m</span></span>, ..."
        heights_section = re.search(
            r"alturas das marés.*?</div>", text, re.S
        )
        if heights_section:
            h_matches = re.findall(
                r"<span class=['\"](?:rojo|azul)['\"]>([\d,]+)",
                heights_section.group(0),
            )
            if h_matches and len(h_matches) == len(tides):
                for i, h in enumerate(h_matches):
                    tides[i]["height"] = h.replace(",", ".") + "m"

        # Sun times — wrapped in <span class='naranja'>
        sun_match = re.search(
            r"amanheceu.*?<span[^>]*>(\d{1,2}:\d{2})", text
        )
        sunset_match = re.search(
            r"pôr do sol.*?<span[^>]*>(\d{1,2}:\d{2})", text
        )
        if sun_match:
            result["sunrise"] = sun_match.group(1)
        if sunset_match:
            result["sunset"] = sunset_match.group(1)

        # Coeficients
        coef_section = re.search(
            r"COEFICIENTE DE MARÉS.*?MANHÃ.*?(\d{2,3}).*?TARDE.*?(\d{2,3})", text, re.S
        )
        if coef_section:
            result["coeficients"] = [coef_section.group(1), coef_section.group(2)]

        return result

    # --- Maré SISBOM ---

    def mare_sisbom(self, date: str | None = None) -> dict:
        """Get tide data from SISBOM API (Natal/RN reference).

        Uses the same Cloud Function the SISBOM Angular app uses.
        Returns 3 days of tide data (yesterday, today, tomorrow).

        Args:
            date: Date in YYYY-MM-DD format. None = today.

        Returns:
            Dict with date, location, heights (list of {time, height}).
        """
        from datetime import date as date_cls

        if not date:
            date = date_cls.today().strftime("%Y-%m-%d")

        url = f"{self._api_url}/ws/tide_table/{date}"
        r = self._http.get(url, timeout=15)
        if r.status_code != 200:
            raise RuntimeError(f"Failed to fetch SISBOM tide data: HTTP {r.status_code}")

        data = r.json()
        # API returns 3 days: [yesterday, today, tomorrow]
        today_data = None
        for entry in data:
            if entry.get("date") == date:
                today_data = entry
                break

        if not today_data and data:
            today_data = data[1] if len(data) > 1 else data[0]

        return {
            "date": date,
            "location": "Natal/RN",
            "source": "sisbom",
            "heights": today_data.get("heights", []) if today_data else [],
            "all_days": data,
        }

    # --- BGs ---

    def list_bgs(self, year: str | None = None, bg_num: str | None = None) -> list[dict]:
        """List Boletins Gerais.

        Args:
            year: Filter by year (e.g. "2026"). None = all years.
            bg_num: Filter by BG number (e.g. "040").

        Returns:
            List of BG dicts with _id, bg_num, year, date_ref, url, filename.
        """
        variables: dict[str, Any] = {}
        if year:
            variables["year"] = year
        if bg_num:
            variables["bg_num"] = bg_num

        query = """query Docs($year: String, $bg_num: String) {
            Docs(year: $year, bg_num: $bg_num) {
                _id
                bg_num
                year
                date_ref
                url
                filename
                n_words
            }
        }"""

        result = self._gql_url(API_BG, query, variables=variables or None)
        docs = result.get("Docs", [])

        # Sort by year desc, bg_num desc
        def sort_key(d: dict) -> tuple:
            try:
                return (-int(d.get("year", 0)), -int(d.get("bg_num", "0").replace(" ", "").split()[0]))
            except (ValueError, TypeError):
                return (0, 0)

        return sorted(docs, key=sort_key)

    def download_bg(self, bg: dict, dest_dir: str | None = None) -> str:
        """Download a BG PDF to dest_dir.

        Args:
            bg: BG dict from list_bgs().
            dest_dir: Destination directory (default: ~/Downloads).

        Returns:
            Path to downloaded file.
        """
        import time
        from pathlib import Path

        url = bg.get("url", "")
        if not url:
            raise ValueError(f"BG {bg.get('bg_num')} has no URL")

        dest = Path(dest_dir) if dest_dir else Path.home() / "Downloads"
        dest.mkdir(parents=True, exist_ok=True)

        # Build filename: BG_040_2026.pdf or BG_Adit_039_2026.pdf
        bg_num = bg.get("bg_num", "").strip()
        year = bg.get("year", "")
        safe_num = bg_num.replace(" ", "_")
        filename = f"BG_{safe_num}_{year}.pdf"
        out_path = dest / filename

        if out_path.exists():
            return str(out_path)

        r = self._http.get(url, timeout=60)
        if r.status_code != 200:
            raise RuntimeError(f"Download failed: HTTP {r.status_code}")

        out_path.write_bytes(r.content)
        return str(out_path)

    # --- GraphQL Core ---

    def _gql_url(
        self,
        base_url: str,
        query: str,
        *,
        variables: dict | None = None,
    ) -> dict:
        """Execute a GraphQL query against an arbitrary base URL."""
        self._ensure_auth()
        return self._gql_url_raw(base_url, query, variables=variables, _retry=True)

    def _gql_url_raw(
        self,
        base_url: str,
        query: str,
        *,
        variables: dict | None = None,
        _retry: bool = False,
    ) -> dict:
        """Internal: execute GraphQL against arbitrary URL, with optional 1x retry on auth error."""
        payload: dict[str, Any] = {"query": query}
        if variables:
            payload["variables"] = variables

        headers = dict(self._http.headers)
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"

        r = self._http.post(
            f"{base_url}/graphql",
            json=payload,
            headers=headers,
        )

        # Auth error on HTTP level → retry once
        if _retry and r.status_code in (401, 403):
            self._token = None
            self.login()
            return self._gql_url_raw(base_url, query, variables=variables, _retry=False)

        if r.status_code != 200:
            raise RuntimeError(f"API error: HTTP {r.status_code} — {r.text[:200]}")

        data = r.json()
        if "errors" in data:
            msg = "; ".join(e.get("message", str(e)) for e in data["errors"])
            # Auth error on GraphQL level → retry once
            if _retry and any(kw in msg.lower() for kw in _AUTH_ERROR_KEYWORDS):
                self._token = None
                self.login()
                return self._gql_url_raw(base_url, query, variables=variables, _retry=False)
            raise RuntimeError(f"GraphQL error: {msg}")

        return data.get("data", {})

    def _gql(
        self,
        query: str,
        *,
        variables: dict | None = None,
        endpoint: str = "graphql",
    ) -> dict:
        """Execute a GraphQL query/mutation.

        Automatically ensures a valid token is present before executing.
        On auth errors (HTTP 401/403 or GraphQL auth message), refreshes token
        and retries once.

        Args:
            query: GraphQL query string.
            variables: Query variables.
            endpoint: API endpoint ('graphql' or 'auth').

        Returns:
            The 'data' dict from the response.

        Raises:
            RuntimeError: On GraphQL errors.
        """
        self._ensure_auth()
        return self._gql_raw(query, variables=variables, endpoint=endpoint, _retry=True)

    def _gql_raw(
        self,
        query: str,
        *,
        variables: dict | None = None,
        endpoint: str = "graphql",
        _retry: bool = False,
    ) -> dict:
        """Internal: execute GraphQL, with optional 1x retry on auth error."""
        payload: dict[str, Any] = {"query": query}
        if variables:
            payload["variables"] = variables

        headers = dict(self._http.headers)
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"

        r = self._http.post(
            f"{self._api_url}/{endpoint}",
            json=payload,
            headers=headers,
        )

        # Auth error on HTTP level → retry once
        if _retry and r.status_code in (401, 403):
            self._token = None
            self.login()
            return self._gql_raw(query, variables=variables, endpoint=endpoint, _retry=False)

        if r.status_code != 200:
            raise RuntimeError(f"API error: HTTP {r.status_code} — {r.text[:200]}")

        data = r.json()

        if "errors" in data:
            errors = data["errors"]
            msg = "; ".join(e.get("message", str(e)) for e in errors)
            # Auth error on GraphQL level → retry once
            if _retry and any(kw in msg.lower() for kw in _AUTH_ERROR_KEYWORDS):
                self._token = None
                self.login()
                return self._gql_raw(query, variables=variables, endpoint=endpoint, _retry=False)
            raise RuntimeError(f"GraphQL error: {msg}")

        return data.get("data", {})

    # --- E-Funcional ---

    def efuncional(
        self,
        str_matricula: str | None = None,
        *,
        dest_dir: str | None = None,
    ) -> dict:
        """Export e-Funcional as PDF.

        Args:
            str_matricula: Military registration number. If None, uses logged-in user.
            dest_dir: Destination directory for PDF. Defaults to current dir.

        Returns:
            Dict with path, hash, verify, crc keys.
        """
        from datetime import datetime, timezone, timedelta
        from pathlib import Path

        # Step 1: Get user ID and matricula
        me = self.me()
        if not me:
            raise RuntimeError("Não autenticado — rode login primeiro")
        user_id = me["_id"]

        # Step 2: Get funcional data (hash)
        query_vars: dict[str, str] = {}
        if str_matricula:
            query_vars["str_matricula"] = str_matricula

        q = "query($str_matricula: String)"  if str_matricula else "query"
        args = "(str_matricula: $str_matricula)" if str_matricula else ""

        result = self._gql(
            f"""{q} {{
                FuncionalValida{args} {{
                    _id str_patente str_quadro str_nomeguerra
                    str_matricula hash
                    expedicao_id {{ local data }}
                }}
            }}""",
            variables=query_vars or None,
        )

        funcional = result.get("FuncionalValida")
        if not funcional or not funcional.get("hash"):
            raise RuntimeError("E-Funcional não encontrada para essa matrícula")

        func_hash = funcional["hash"]
        nome = funcional.get("str_nomeguerra", "militar")
        patente = funcional.get("str_patentesigla") or funcional.get("str_patente", "")
        matricula = funcional.get("str_matricula", "")

        # Step 3: LogPrint mutation to get temporary print hash
        tz = timezone(timedelta(hours=-3))
        now = datetime.now(tz).isoformat()

        print_result = self._gql(
            """mutation LogPrint($data: String, $type: String, $_user: String, $args: String, $printed_at: String){
                LogPrint(data: $data, type: $type, _user: $_user, args: $args, printed_at: $printed_at){
                    _id hash verify crc
                }
            }""",
            variables={
                "type": "militar-funcional",
                "_user": user_id,
                "args": json.dumps({"hash": func_hash}),
                "printed_at": now,
            },
        )

        log_print = print_result.get("LogPrint")
        if not log_print or not log_print.get("hash"):
            raise RuntimeError("Falha ao gerar hash de impressão (LogPrint)")

        print_hash = log_print["hash"]

        # Step 4: Download PDF from doc_print endpoint
        headers = {}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"

        r = self._http.get(
            f"{self._api_url}/reports/doc_print?hash={print_hash}",
            headers=headers,
        )

        if r.status_code != 200 or len(r.content) < 100:
            raise RuntimeError(f"Falha ao baixar PDF: HTTP {r.status_code}, {len(r.content)} bytes")

        # Step 5: Save PDF
        out_dir = Path(dest_dir) if dest_dir else Path(".")
        out_dir.mkdir(parents=True, exist_ok=True)
        filename = f"efuncional_{nome.lower()}_{matricula}.pdf"
        out_path = out_dir / filename
        out_path.write_bytes(r.content)

        return {
            "path": str(out_path),
            "size": len(r.content),
            "nome": nome,
            "patente": patente,
            "matricula": matricula,
            "hash": func_hash,
            "print_hash": print_hash,
            "verify": log_print.get("verify"),
            "crc": log_print.get("crc"),
        }

    def efuncional_list(self, str_matricula: str | None = None) -> list[dict]:
        """List all e-Funcional emissions for a military member."""
        query_vars: dict[str, str] = {}
        if str_matricula:
            query_vars["str_matricula"] = str_matricula

        q = "query($str_matricula: String)" if str_matricula else "query"
        args = "(str_matricula: $str_matricula)" if str_matricula else ""

        result = self._gql(
            f"""{q} {{
                MilitarFuncionals{args} {{
                    _id str_patente str_quadro str_nomeguerra
                    str_matricula hash active
                }}
            }}""",
            variables=query_vars or None,
        )

        return result.get("MilitarFuncionals", [])

    def raw_query(self, query: str, variables: dict | None = None) -> dict:
        """Execute a raw GraphQL query and return full data dict."""
        return self._gql(query, variables=variables)

    def introspect_type(self, type_name: str) -> dict:
        """Introspect a GraphQL type to discover its fields."""
        result = self._gql(
            """query IntrospectType($name: String!) {
                __type(name: $name) {
                    name
                    kind
                    fields {
                        name
                        type {
                            name
                            kind
                            ofType { name kind }
                        }
                    }
                }
            }""",
            variables={"name": type_name},
        )
        return result.get("__type", {})
