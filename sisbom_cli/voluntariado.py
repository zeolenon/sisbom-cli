"""SISDO volunteer reads, plans and explicit additive enrollment."""
from __future__ import annotations
import hashlib
import json
import re
import fcntl
from pathlib import Path
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import urlsplit, urljoin, parse_qs
import httpx
from .auth import load_token
from .client import SISBOMClient
from .sisdo import SISDOClient, BASE_URL, _Forms, _text, matricula_digits

LIST_PATH = '/sisdo/voluntariado'
USER_PATH = '/usuario/voluntariado'
QUARTEIS = {'assu': '11667', 'apodi': '11662', 'pau-dos-ferros': '11661', 'mossoro': '11660'}
MESES = 'janeiro fevereiro março abril maio junho julho agosto setembro outubro novembro dezembro'.split()


def competencia(value: str) -> str:
    if not re.fullmatch(r'\d{4}-\d{2}(?:-01)?', value):
        raise ValueError('Competência deve ser AAAA-MM ou AAAA-MM-01.')
    datetime.strptime(value[:7], '%Y-%m')
    return value[:7] + '-01'


class _DOM(HTMLParser):
    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.rows, self.links, self.inputs, self.buttons, self.labels = [], [], [], [], {}
        self.row = self.cell = self.label = self.button = None
        self.in_table = 0
        self.headers = []
        self.header = None
        self.feed(html)
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'table': self.in_table += 1
        if tag == 'tr' and self.in_table: self.row = []
        if tag == 'td' and self.row is not None: self.cell = []
        if tag == 'th' and self.in_table: self.header = []
        if tag == 'a': self.links.append(a)
        if tag == 'input': self.inputs.append(a)
        if tag == 'button': self.button = (a, [])
        if tag == 'label': self.label = (a.get('for'), [])
    def handle_data(self, data):
        for target in (self.cell, self.header):
            if target is not None: target.append(data)
        if self.label: self.label[1].append(data)
        if self.button: self.button[1].append(data)
    def handle_endtag(self, tag):
        if tag == 'td' and self.cell is not None:
            self.row.append(' '.join(''.join(self.cell).split())); self.cell = None
        if tag == 'th' and self.header is not None:
            self.headers.append(' '.join(''.join(self.header).split())); self.header = None
        if tag == 'tr' and self.row is not None:
            if self.row: self.rows.append(self.row)
            self.row = None
        if tag == 'table': self.in_table -= 1
        if tag == 'label' and self.label:
            self.labels[self.label[0]] = ' '.join(''.join(self.label[1]).split()); self.label = None
        if tag == 'button' and self.button:
            self.buttons.append((self.button[0], ' '.join(''.join(self.button[1]).split()))); self.button = None


def parse_list(html: str, unit: str, month: str) -> dict:
    month = competencia(month)
    if 'Voluntários para Diária Operacional por Lotação' not in _text(html):
        raise RuntimeError('Página de voluntariado ausente; sessão, permissão ou resposta inesperada.')
    forms = _Forms(html).forms
    filters = [f for f in forms if urlsplit(f.action).path == LIST_PATH and f.method == 'get']
    if len(filters) != 1: raise RuntimeError('Filtro de voluntariado ausente ou ambíguo.')
    f = filters[0]
    if f.values.get('lotacao_id') != unit or f.values.get('mes_referencia') != month:
        raise RuntimeError('Servidor não confirmou quartel/competência solicitados.')
    label = dict(f.options.get('lotacao_id', [])).get(unit)
    if not label: raise RuntimeError('Quartel não oferecido pela sessão.')
    dom = _DOM(html)
    if dom.headers != ['Nome', 'Matrícula', 'Graduação', 'Lotação atual']:
        raise RuntimeError('Colunas de voluntariado inesperadas.')
    exports = [b for b in dom.buttons if 'Exportar / Gerar Lista Definitiva' in b[1]]
    export_forms = [f for f in forms if urlsplit(f.action).path == LIST_PATH + '/exportar' and f.method == 'post']
    if len(exports) != 1 or len(export_forms) != 1:
        raise RuntimeError('Estado do ciclo não reconhecido.')
    state = 'provisoria' if 'disabled' in exports[0][0] else 'definitiva_disponivel'
    members = {}
    duplicates = 0
    for row in dom.rows:
        if len(row) == 1 and row[0] == 'Nenhum voluntário para esta lotação neste ciclo.':
            if len(dom.rows) != 1: raise RuntimeError('Resposta vazia contraditória.')
            continue
        if len(row) != 4: raise RuntimeError('Linha de voluntário não reconhecida.')
        registration = matricula_digits(row[1])
        if not re.fullmatch(r'\d{7}', registration): raise RuntimeError('Matrícula inválida na lista.')
        member = dict(competencia=month[:7], quartel_id=unit, quartel_interesse=label,
                      matricula=registration, nome=row[0], graduacao=row[2], lotacao_atual=row[3])
        if registration in members:
            if members[registration] != member: raise RuntimeError('Inscrições duplicadas com dados conflitantes.')
            duplicates += 1
        members[registration] = member
    if not dom.rows: raise RuntimeError('Tabela sem registros nem indicação explícita de lista vazia.')
    next_pages = []
    for link in dom.links:
        href = link.get('href') or ''
        p = urlsplit(urljoin(BASE_URL, href))
        if 'page' in parse_qs(p.query):
            raise RuntimeError('Paginação detectada; extração interrompida para não devolver lista parcial.')
    return dict(competencia=month[:7], quartel_id=unit, quartel_interesse=label,
                situacao=state, lista_definitiva_gerada=False, total=len(members),
                duplicatas_descartadas=duplicates, militares=list(members.values()))


def parse_profile(html: str) -> dict:
    text = _text(html)
    match = re.search(r'Voluntariado para Diária Operacional\s*[—–-]\s*([a-zç]+)/([0-9]{4})', text)
    if not match or match[1] not in MESES:
        raise RuntimeError('Competência de inscrição não reconhecida.')
    forms = [f for f in _Forms(html).forms if urlsplit(f.action).path == USER_PATH and f.method == 'post']
    if len(forms) != 1: raise RuntimeError('Formulário de inscrição ausente ou ambíguo; ciclo possivelmente fechado.')
    form = forms[0]
    if urljoin(BASE_URL, form.action) != BASE_URL + USER_PATH:
        raise RuntimeError('Destino de inscrição inesperado.')
    dom = _DOM(html)
    radios = [i for i in dom.inputs if i.get('name') == 'bo_voluntario']
    choices = [i for i in dom.inputs if i.get('name') == 'lotacoes[]']
    if {i.get('value') for i in radios} != {'0','1'} or not choices:
        raise RuntimeError('Campos de inscrição não reconhecidos.')
    selected = [i['value'] for i in radios if 'checked' in i]
    if len(selected) > 1: raise RuntimeError('Resposta individual ambígua.')
    units = sorted({i['value'] for i in choices if 'checked' in i})
    available = {i['value']: dom.labels.get(i.get('id'), i['value']) for i in choices if 'disabled' not in i}
    buttons = [b for b in dom.buttons if b[1] == 'Salvar resposta']
    opened = len(buttons) == 1 and 'disabled' not in buttons[0][0]
    return dict(competencia=f'{match[2]}-{MESES.index(match[1])+1:02}',
                resposta=selected[0] if selected else None, quarteis=units,
                quarteis_disponiveis=available, aberto=opened,
                elegibilidade='Somente opções oferecidas pela sessão; regras adicionais do servidor não verificadas.',
                semantica_envio='Conjunto completo; confirmar por releitura após envio, sem garantia de concorrência transacional.')


def plan_profile(current: dict, month: str, units: list[str], mode: str, allow_removal=False) -> dict:
    if current['competencia'] != competencia(month)[:7]: raise ValueError('Competência solicitada difere do ciclo aberto no perfil.')
    if not current['aberto']: raise RuntimeError('Ciclo não está aberto para resposta.')
    if mode not in ('adicionar','remover','substituir'): raise ValueError('Modo desconhecido.')
    requested = set(units)
    if not requested: raise ValueError('Informe quartéis explicitamente.')
    if not requested <= current['quarteis_disponiveis'].keys(): raise ValueError('Quartel não disponível no formulário atual.')
    before = set(current['quarteis'])
    after = before | requested if mode == 'adicionar' else before - requested if mode == 'remover' else requested
    removed = sorted(before - after)
    if removed and not allow_removal: raise ValueError('Prévia removeria inscrições; use --permitir-remocao para revisar explicitamente.')
    if not after: raise ValueError('Conjunto vazio recusado: retirada total exige fluxo específico ainda não implementado.')
    plan = dict(competencia=current['competencia'], modo=mode, antes=sorted(before), depois=sorted(after),
                adicionados=sorted(after-before), removidos=removed, resposta_antes=current['resposta'], resposta_depois='1',
                executado=False, envio_habilitado=False, rota_post=USER_PATH,
                campos_publicos={'bo_voluntario':'1','lotacoes[]':sorted(after)},
                limite='Somente prévia. Para inclusão use voluntariado-inscrever; retirada/substituição não têm comando de envio.')
    plan['hash_previa'] = hashlib.sha256(json.dumps(plan, sort_keys=True).encode()).hexdigest()
    return plan


class VoluntariadoClient(SISDOClient):
    def connect(self):
        if self._authenticated: return
        token = load_token()
        if not token: raise RuntimeError('Sessão SISBOM vigente ausente; autenticação explícita necessária. Nenhuma renovação feita.')
        try:
            with SISBOMClient(api_url='https://sisbom.cbm.rn.gov.br/api') as source:
                source._token = token
                data = source._gql_raw('mutation CreateSsoTicket($target: String) { CreateSsoTicket(target: $target) { token } }', variables={'target':'sisdo'}, _retry=False)
            ticket = (data.get('CreateSsoTicket') or {}).get('token')
            if not ticket: raise RuntimeError('Ticket ausente')
            response = self._request('GET', '/', params={'ticket':ticket})
            if response.url.path != '/home' or 'sisdo_session' not in self._http.cookies:
                raise RuntimeError('Sessão não confirmada')
        except (RuntimeError, httpx.HTTPError, ValueError):
            raise RuntimeError('Acesso SSO não confirmado; sessão expirada, permissão ou serviço indisponível. Nenhuma renovação feita.') from None
        self._authenticated = True

    def list_volunteers(self, month, units):
        month = competencia(month)
        if not units: raise ValueError('Informe pelo menos um quartel.')
        ids = sorted(set(QUARTEIS.get(u,u) for u in units))
        if any(not re.fullmatch(r'\d+', u) for u in ids): raise ValueError('Quartel inválido.')
        self.connect()
        lists = []
        for unit in ids:
            response = self._request('GET', LIST_PATH, params={'lotacao_id':unit,'mes_referencia':month})
            result = parse_list(response.text, unit, month)
            result['fonte'] = str(response.url)
            lists.append(result)
        return dict(competencia=month[:7], coletado_em=datetime.now(timezone.utc).isoformat(),
                    listas=lists, total_vinculos=sum(x['total'] for x in lists),
                    total_militares=len({m['matricula'] for x in lists for m in x['militares']}))

    def profile(self):
        self.connect()
        result = parse_profile(self._request('GET', USER_PATH).text)
        result['fonte'] = BASE_URL + USER_PATH
        return result

    def enroll(self, month, units, *, execute=False, expected_hash=None, journal=None):
        """Add only to the current user's selections; never withdraw or retry POST."""
        self.connect()
        html = self._request('GET', USER_PATH).text
        before = parse_profile(html)
        requested = [QUARTEIS.get(u, u) for u in units]
        plan = plan_profile(before, month, requested, 'adicionar')
        if expected_hash and expected_hash != plan['hash_previa']:
            raise RuntimeError('Perfil mudou desde a prévia; nenhum envio realizado.')
        result = {**plan, 'envio_habilitado': True,
                  'limite': 'Inclusão do próprio usuário; substituição/retirada e exportação não habilitadas. Conferência por perfil após POST.'}
        if not execute:
            return result
        if not journal:
            raise ValueError('Execução exige --diario privado, preservado para reconciliação.')
        path = Path(journal)
        path.parent.mkdir(parents=True, exist_ok=True)
        key = hashlib.sha256(json.dumps([plan['competencia'], sorted(set(requested))]).encode()).hexdigest()
        with Path(str(path) + '.lock').open('a') as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise RuntimeError('Outro envio usa este diário; interrompido.') from None
            state = json.loads(path.read_text()) if path.exists() else {'operacoes': {}}
            def save():
                temporary = Path(str(path) + '.tmp')
                temporary.touch(mode=0o600, exist_ok=True)
                temporary.chmod(0o600)
                temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2))
                temporary.replace(path)
            previous = state['operacoes'].get(key)
            if previous:
                if (before['resposta'] == '1' and before['competencia'] == previous['competencia']
                        and set(before['quarteis']) == set(previous['depois'])):
                    previous['fase'] = 'confirmado'
                    save()
                    return {**result, 'executado': False, 'confirmado': True, 'idempotente': True}
                raise RuntimeError('Operação anterior não reconciliada ou perfil divergente; consulte perfil/diário, não repetir envio.')
            if before['resposta'] == '1' and set(before['quarteis']) == set(plan['depois']):
                return {**result, 'executado': False, 'confirmado': True, 'idempotente': True}
            # Re-read immediately before submitting and use the current form's CSRF.
            fresh_html = self._request('GET', USER_PATH).text
            fresh = parse_profile(fresh_html)
            if plan_profile(fresh, month, requested, 'adicionar')['hash_previa'] != plan['hash_previa']:
                raise RuntimeError('Perfil mudou durante a preparação; nenhum envio realizado.')
            forms = [f for f in _Forms(fresh_html).forms if f.method == 'post' and urljoin(BASE_URL, f.action) == BASE_URL + USER_PATH]
            if len(forms) != 1 or set(forms[0].controls) != {'_token', 'bo_voluntario', 'lotacoes[]'} or not forms[0].values.get('_token'):
                raise RuntimeError('Contrato/CSRF do formulário mudou; nenhum envio realizado.')
            entry = {'competencia': plan['competencia'], 'antes': plan['antes'], 'depois': plan['depois'],
                     'hash_previa': plan['hash_previa'], 'fase': 'envio_iniciado',
                     'inicio_utc': datetime.now(timezone.utc).isoformat()}
            state['operacoes'][key] = entry
            save()  # intent before the single POST; CSRF never persisted
            try:
                response = self._http.post(BASE_URL + USER_PATH,
                    data={'_token': forms[0].values['_token'], 'bo_voluntario': '1', 'lotacoes[]': plan['depois']},
                    headers={'Referer': BASE_URL + USER_PATH})
                if response.is_redirect:
                    target = urljoin(str(response.url), response.headers.get('location', ''))
                    if response.status_code not in (302,303) or target != BASE_URL + USER_PATH:
                        raise RuntimeError('Resposta de envio não confirmada.')
                elif response.status_code != 200:
                    raise RuntimeError('Resposta de envio não confirmada.')
                after = self.profile()
                if (after['competencia'] != plan['competencia'] or after['resposta'] != '1'
                        or set(after['quarteis']) != set(plan['depois'])):
                    raise RuntimeError('Perfil não confirmou integralmente a inscrição.')
            except (httpx.HTTPError, RuntimeError, ValueError):
                entry['fase'] = 'reconciliacao_necessaria'
                save()
                raise RuntimeError('Inscrição não confirmada. Consulte voluntariado-perfil e preserve diário; nenhum POST será repetido automaticamente.') from None
            entry.update(fase='confirmado', fim_utc=datetime.now(timezone.utc).isoformat())
            save()
            return {**result, 'executado': True, 'confirmado': True, 'perfil_confirmado': after}
