import { createContext, useCallback, useContext, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { ApiError } from './api'
import type { Movement, MovementType } from './api'

export type Locale = 'pt-PT' | 'en-GB'

const pt = {
  'nav.items': 'Itens',
  'nav.movements': 'Movimentos',
  'nav.import': 'Importação',

  'status.connecting': 'A ligar…',
  'status.online': 'Servidor local: ligado',
  'status.offline': 'Servidor local: sem ligação',
  'status.waiting': 'A aguardar o servidor local…',
  'theme.label': 'Tema',
  'theme.light': 'Claro',
  'theme.dark': 'Escuro',
  'locale.label': 'Idioma',

  'common.back': '← Voltar',
  'common.backToList': '← Voltar à lista',
  'common.previous': 'Anterior',
  'common.next': 'Seguinte',
  'common.loading': 'A carregar…',
  'common.processing': 'A processar…',
  'common.optional': 'Opcional',
  'common.name': 'Nome',
  'common.none': '—',

  'items.title': 'Itens',
  'items.count': '{count} itens',
  'items.search': 'Pesquisar descrição, referência, EAN, marca ou id',
  'items.stock.all': 'Todos',
  'items.stock.in': 'Com stock',
  'items.stock.zero': 'Sem stock',
  'items.shelf.all': 'Todas as estantes',
  'items.shelf.label': 'Estante {n}',
  'items.empty': 'Nenhum item encontrado.',
  'items.range': '{from}–{to} de {total}',
  'items.col.id': 'Id',
  'items.col.description': 'Descrição',
  'items.col.brand': 'Marca',
  'items.col.reference': 'Referência',
  'items.col.stock': 'Stock',
  'items.col.location': 'Localização',
  'items.col.verified': 'Verificado',
  'items.noLocation': 'Sem localização',

  'item.data': 'Dados',
  'item.fact.brand': 'Marca',
  'item.fact.reference': 'Referência',
  'item.fact.ean': 'EAN',
  'item.fact.serial': 'Nº de série',
  'item.fact.verified': 'Verificado',
  'item.verifyButton': 'Marcar como verificado',
  'item.stockTitle': 'Stock: {total}',
  'item.noStock': 'Sem stock registado.',
  'item.col.location': 'Localização',
  'item.col.qty': 'Qtd.',
  'item.record': 'Registar movimento',
  'item.field.type': 'Tipo',
  'item.field.qty': 'Quantidade',
  'item.field.counted': 'Quantidade contada',
  'item.field.from': 'Origem',
  'item.field.to': 'Destino',
  'item.field.location': 'Localização',
  'item.field.countedLocation': 'Localização contada',
  'item.field.reason': 'Motivo / nota',
  'item.field.operator': 'Operador',
  'item.pick': 'Escolher…',
  'item.from.auto': 'Automática (se só houver um sítio)',
  'item.to.none': 'Sem localização',
  'item.submit': 'Registar',
  'item.notice.recorded': 'Movimento registado.',
  'item.notice.nochange': 'Sem alterações: a contagem já estava correta.',
  'item.notice.verified': 'Item verificado.',
  'item.history': 'Histórico',
  'item.noMovements': 'Sem movimentos.',
  'item.col.date': 'Data',
  'item.col.type': 'Tipo',
  'item.col.fromTo': 'De → Para',
  'item.col.operator': 'Operador',
  'item.col.source': 'Origem',
  'item.reasonPlaceholder': 'Opcional',
  'item.namePlaceholder': 'Nome',

  'movements.title': 'Movimentos',
  'movements.allTypes': 'Todos os tipos',
  'movements.allSources': 'Todas as origens',
  'movements.empty': 'Sem movimentos.',
  'movements.col.date': 'Data',
  'movements.col.type': 'Tipo',
  'movements.col.item': 'Item',
  'movements.col.qty': 'Qtd.',
  'movements.col.fromTo': 'De → Para',
  'movements.col.operator': 'Operador',
  'movements.col.source': 'Origem',

  'import.title': 'Importação',
  'import.help':
    'Importa uma folha de inventário (.xlsx). Primeiro faça a análise, depois importe. Reimportar é seguro: só as diferenças de stock são registadas.',
  'import.analyse': 'Analisar',
  'import.import': 'Importar',
  'import.confirm': 'Importar este ficheiro para a base de dados?',
  'import.done': 'Importação concluída.',
  'import.resultTitle': 'Resultado',
  'import.analysisTitle': 'Análise',
  'import.issuesTitle': 'Pontos a rever',
  'import.sheet': 'Folha',
  'import.rows': 'Linhas',
  'import.newItems': 'Itens novos',
  'import.updatedItems': 'Itens atualizados',
  'import.adjusted': 'Ajustes de stock',

  'type.IN': 'Entrada',
  'type.OUT': 'Saída',
  'type.MOVE': 'Transferência',
  'type.ADJUST': 'Ajuste (contagem)',
  'type.VERIFY': 'Verificação',
  'type.IMPORT': 'Importação',
  'source.local': 'Local',
  'source.mobile': 'Telemóvel',
  'source.import': 'Importação',

  'errors.network': 'Não foi possível contactar o servidor local.',
  'errors.generic': 'Erro {status}',
  'errors.loadItems': 'Erro ao carregar itens',
  'errors.loadItem': 'Erro ao carregar o item',
  'errors.loadMovements': 'Erro ao carregar movimentos',
  'errors.register': 'Erro ao registar o movimento',
  'errors.verify': 'Erro ao verificar',
  'errors.import': 'Erro na importação',
  'errors.notFound': 'Item não encontrado',
  'errors.save': 'Erro ao guardar',
  'errors.delete': 'Erro ao eliminar',
  'errors.void': 'Erro ao anular',
  'errors.locations': 'Erro ao carregar localizações',

  'nav.locations': 'Localizações',
  'items.new': 'Novo item',
  'items.export': 'Exportar Excel',
  'errors.export': 'Erro ao exportar o ficheiro',
  'items.status.active': 'Ativos',
  'items.status.inactive': 'Inativos',
  'items.status.all': 'Todos os estados',

  'form.new': 'Novo item',
  'form.edit': 'Editar item',
  'form.id': 'Id (vazio = automático)',
  'form.description': 'Descrição',
  'form.brand': 'Marca',
  'form.reference': 'Referência',
  'form.ean': 'EAN',
  'form.serial': 'Nº de série',
  'form.notes': 'Notas',
  'form.initialQty': 'Stock inicial',
  'form.initialLocation': 'Localização inicial',
  'form.save': 'Guardar',
  'form.cancel': 'Cancelar',
  'form.required': 'A descrição é obrigatória.',

  'item.edit': 'Editar',
  'item.delete': 'Eliminar item',
  'item.deleteConfirm': 'Eliminar este item? Fica inativo e o histórico é mantido.',
  'item.deleteBlocked': 'Para eliminar, primeiro retire o stock.',
  'item.reactivate': 'Reativar',
  'item.inactive': 'Inativo',
  'item.void': 'Anular',
  'item.voidConfirm': 'Anular este movimento? Será registado um movimento de reposição; o original fica no histórico.',
  'item.notice.saved': 'Alterações guardadas.',
  'item.notice.deleted': 'Item eliminado.',
  'item.notice.reactivated': 'Item reativado.',
  'item.notice.voided': 'Movimento anulado.',
  'item.unverifyButton': 'Desmarcar verificação',
  'item.notice.unverified': 'Verificação removida.',

  'locations.title': 'Localizações',
  'locations.new': 'Nova localização',
  'locations.estante': 'Estante',
  'locations.prateleira': 'Prateleira',
  'locations.prateleiraHint': 'ex.: 2, 3, 4 ou Topo',
  'locations.add': 'Adicionar',
  'locations.edit': 'Editar',
  'locations.delete': 'Eliminar',
  'locations.deleteConfirm': 'Eliminar esta localização?',
  'locations.empty': 'Sem localizações.',
  'locations.col.label': 'Localização',
  'locations.col.actions': 'Ações',
  'locations.notice.saved': 'Localização guardada.',
  'locations.notice.deleted': 'Localização eliminada.',
  'locations.unassignedNote': 'A localização "Sem localização" é reservada e não pode ser alterada.',
  'locations.noShelf': 'Sem prateleira',
  'import.source': 'Origem do ficheiro',
  'import.source.local': 'Ficheiro local',
  'import.source.sharepoint': 'SharePoint',
  'import.source.label': 'Origem',
  'import.sp.notConfigured':
    'SharePoint não configurado: defina client_id em data/sharepoint.json (ver docs/SPEC.md §6.4).',
  'import.sp.notSignedIn': 'Ainda não iniciou sessão no SharePoint.',
  'import.sp.signIn': 'Iniciar sessão no SharePoint',
  'import.sp.openLink': 'Abra',
  'import.sp.enterCode': 'e introduza o código',
  'import.sp.waiting': 'À espera que inicie sessão…',
  'import.sp.signedInAs': 'Sessão iniciada como {account}',
  'import.sp.link': 'Ficheiro a sincronizar (ligação do SharePoint)',
  'import.sp.saveLink': 'Guardar ligação',
  'import.sp.linkSaved': 'Ligação guardada.',
  'import.sp.signOut': 'Terminar sessão',
  'import.sp.signedOut': 'Sessão terminada neste PC.',
  'clear.title': 'Apagar dados locais',
  'clear.warning':
    'Isto apaga TODOS os itens, localizações, stock e histórico de movimentos guardados neste PC. Não é possível desfazer. A folha no SharePoint não é alterada, e a sessão e a ligação ao SharePoint mantêm-se.',
  'clear.hint': 'Para confirmar, escreva {word}',
  'clear.word': 'APAGAR',
  'clear.confirmButton': 'Apagar tudo',
  'clear.done': 'Dados locais apagados. Já pode importar uma nova folha.',
  'import.alt.title': 'Procedimento alternativo de correção',
  'import.alt.step1':
    'No SharePoint, abra a biblioteca que contém o ficheiro e clique em Sincronizar (Sync). Isto cria uma pasta no seu PC que se mantém atualizada.',
  'import.alt.step2': 'Em Importação, escolha Ficheiro local e selecione o Inventário.xlsx dessa pasta sincronizada.',
  'import.alt.step3': 'Analise e importe como habitualmente. Não é preciso iniciar sessão nem ter permissões adicionais.',
}

export type Key = keyof typeof pt

const en: Record<Key, string> = {
  'nav.items': 'Items',
  'nav.movements': 'Movements',
  'nav.import': 'Import',

  'status.connecting': 'Connecting…',
  'status.online': 'Local server: connected',
  'status.offline': 'Local server: not connected',
  'status.waiting': 'Waiting for the local server…',
  'theme.label': 'Theme',
  'theme.light': 'Light',
  'theme.dark': 'Dark',
  'locale.label': 'Language',

  'common.back': '← Back',
  'common.backToList': '← Back to list',
  'common.previous': 'Previous',
  'common.next': 'Next',
  'common.loading': 'Loading…',
  'common.processing': 'Processing…',
  'common.optional': 'Optional',
  'common.name': 'Name',
  'common.none': '—',

  'items.title': 'Items',
  'items.count': '{count} items',
  'items.search': 'Search description, reference, EAN, brand or id',
  'items.stock.all': 'All',
  'items.stock.in': 'In stock',
  'items.stock.zero': 'Out of stock',
  'items.shelf.all': 'All racks',
  'items.shelf.label': 'Rack {n}',
  'items.empty': 'No items found.',
  'items.range': '{from}–{to} of {total}',
  'items.col.id': 'Id',
  'items.col.description': 'Description',
  'items.col.brand': 'Brand',
  'items.col.reference': 'Reference',
  'items.col.stock': 'Stock',
  'items.col.location': 'Location',
  'items.col.verified': 'Verified',
  'items.noLocation': 'No location',

  'item.data': 'Details',
  'item.fact.brand': 'Brand',
  'item.fact.reference': 'Reference',
  'item.fact.ean': 'EAN',
  'item.fact.serial': 'Serial no.',
  'item.fact.verified': 'Verified',
  'item.verifyButton': 'Mark as verified',
  'item.stockTitle': 'Stock: {total}',
  'item.noStock': 'No stock recorded.',
  'item.col.location': 'Location',
  'item.col.qty': 'Qty.',
  'item.record': 'Record movement',
  'item.field.type': 'Type',
  'item.field.qty': 'Quantity',
  'item.field.counted': 'Counted quantity',
  'item.field.from': 'From',
  'item.field.to': 'To',
  'item.field.location': 'Location',
  'item.field.countedLocation': 'Counted location',
  'item.field.reason': 'Reason / note',
  'item.field.operator': 'Operator',
  'item.pick': 'Choose…',
  'item.from.auto': 'Automatic (if there is only one place)',
  'item.to.none': 'No location',
  'item.submit': 'Record',
  'item.notice.recorded': 'Movement recorded.',
  'item.notice.nochange': 'No change: the count was already correct.',
  'item.notice.verified': 'Item verified.',
  'item.history': 'History',
  'item.noMovements': 'No movements.',
  'item.col.date': 'Date',
  'item.col.type': 'Type',
  'item.col.fromTo': 'From → To',
  'item.col.operator': 'Operator',
  'item.col.source': 'Source',
  'item.reasonPlaceholder': 'Optional',
  'item.namePlaceholder': 'Name',

  'movements.title': 'Movements',
  'movements.allTypes': 'All types',
  'movements.allSources': 'All sources',
  'movements.empty': 'No movements.',
  'movements.col.date': 'Date',
  'movements.col.type': 'Type',
  'movements.col.item': 'Item',
  'movements.col.qty': 'Qty.',
  'movements.col.fromTo': 'From → To',
  'movements.col.operator': 'Operator',
  'movements.col.source': 'Source',

  'import.title': 'Import',
  'import.help':
    'Imports an inventory sheet (.xlsx). Analyse it first, then import. Re-importing is safe: only stock differences are recorded.',
  'import.analyse': 'Analyse',
  'import.import': 'Import',
  'import.confirm': 'Import this file into the database?',
  'import.done': 'Import complete.',
  'import.resultTitle': 'Result',
  'import.analysisTitle': 'Analysis',
  'import.issuesTitle': 'Items to review',
  'import.sheet': 'Sheet',
  'import.rows': 'Rows',
  'import.newItems': 'New items',
  'import.updatedItems': 'Updated items',
  'import.adjusted': 'Stock adjustments',

  'type.IN': 'Stock in',
  'type.OUT': 'Stock out',
  'type.MOVE': 'Transfer',
  'type.ADJUST': 'Adjustment (count)',
  'type.VERIFY': 'Verification',
  'type.IMPORT': 'Import',
  'source.local': 'Local',
  'source.mobile': 'Mobile',
  'source.import': 'Import',

  'errors.network': 'Could not reach the local server.',
  'errors.generic': 'Error {status}',
  'errors.loadItems': 'Error loading items',
  'errors.loadItem': 'Error loading the item',
  'errors.loadMovements': 'Error loading movements',
  'errors.register': 'Error recording the movement',
  'errors.verify': 'Error verifying the item',
  'errors.import': 'Import error',
  'errors.notFound': 'Item not found',
  'errors.save': 'Error saving',
  'errors.delete': 'Error deleting',
  'errors.void': 'Error voiding the movement',
  'errors.locations': 'Error loading locations',

  'nav.locations': 'Locations',
  'items.new': 'New item',
  'items.export': 'Export Excel',
  'errors.export': 'Error exporting the file',
  'items.status.active': 'Active',
  'items.status.inactive': 'Inactive',
  'items.status.all': 'All statuses',

  'form.new': 'New item',
  'form.edit': 'Edit item',
  'form.id': 'Id (blank = automatic)',
  'form.description': 'Description',
  'form.brand': 'Brand',
  'form.reference': 'Reference',
  'form.ean': 'EAN',
  'form.serial': 'Serial no.',
  'form.notes': 'Notes',
  'form.initialQty': 'Opening stock',
  'form.initialLocation': 'Opening location',
  'form.save': 'Save',
  'form.cancel': 'Cancel',
  'form.required': 'Description is required.',

  'item.edit': 'Edit',
  'item.delete': 'Delete item',
  'item.deleteConfirm': 'Delete this item? It becomes inactive and its history is kept.',
  'item.deleteBlocked': 'To delete, first remove the stock.',
  'item.reactivate': 'Reactivate',
  'item.inactive': 'Inactive',
  'item.void': 'Void',
  'item.voidConfirm': 'Void this movement? A reversing movement will be recorded; the original stays in the history.',
  'item.notice.saved': 'Changes saved.',
  'item.notice.deleted': 'Item deleted.',
  'item.notice.reactivated': 'Item reactivated.',
  'item.notice.voided': 'Movement voided.',
  'item.unverifyButton': 'Remove verification',
  'item.notice.unverified': 'Verification removed.',

  'locations.title': 'Locations',
  'locations.new': 'New location',
  'locations.estante': 'Rack',
  'locations.prateleira': 'Shelf',
  'locations.prateleiraHint': 'e.g. 2, 3, 4 or Topo',
  'locations.add': 'Add',
  'locations.edit': 'Edit',
  'locations.delete': 'Delete',
  'locations.deleteConfirm': 'Delete this location?',
  'locations.empty': 'No locations.',
  'locations.col.label': 'Location',
  'locations.col.actions': 'Actions',
  'locations.notice.saved': 'Location saved.',
  'locations.notice.deleted': 'Location deleted.',
  'locations.unassignedNote': '"No location" is reserved and cannot be changed.',
  'locations.noShelf': 'No shelf',
  'import.source': 'File source',
  'import.source.local': 'Local file',
  'import.source.sharepoint': 'SharePoint',
  'import.source.label': 'Source',
  'import.sp.notConfigured':
    'SharePoint is not configured: set client_id in data/sharepoint.json (see docs/SPEC.md §6.4).',
  'import.sp.notSignedIn': 'You have not signed in to SharePoint yet.',
  'import.sp.signIn': 'Sign in to SharePoint',
  'import.sp.openLink': 'Open',
  'import.sp.enterCode': 'and enter the code',
  'import.sp.waiting': 'Waiting for you to sign in…',
  'import.sp.signedInAs': 'Signed in as {account}',
  'import.sp.link': 'File to sync with (SharePoint link)',
  'import.sp.saveLink': 'Save link',
  'import.sp.linkSaved': 'Link saved.',
  'import.sp.signOut': 'Sign out',
  'import.sp.signedOut': 'Signed out on this PC.',
  'clear.title': 'Delete local data',
  'clear.warning':
    'This permanently deletes ALL items, locations, stock and movement history stored on this PC. It cannot be undone. The SharePoint workbook is not changed, and your SharePoint sign-in and link are kept.',
  'clear.hint': 'To confirm, type {word}',
  'clear.word': 'DELETE',
  'clear.confirmButton': 'Delete everything',
  'clear.done': 'Local data deleted. You can now import a new sheet.',
  'import.alt.title': 'Alternative Fix Procedure',
  'import.alt.step1':
    'In SharePoint, open the library that holds the workbook and click Sync. This creates a folder on your PC that stays up to date.',
  'import.alt.step2': 'On Import, choose Local file and select Inventário.xlsx from that synced folder.',
  'import.alt.step3': 'Analyse and import as usual. No sign-in or extra permissions are needed.',
}

const DICTS: Record<Locale, Record<Key, string>> = { 'pt-PT': pt, 'en-GB': en }
const LOCALE_KEY = 'ims.locale'

type TFn = (key: Key, vars?: Record<string, string | number>) => string

type I18nValue = {
  locale: Locale
  setLocale: (locale: Locale) => void
  t: TFn
}

const I18nContext = createContext<I18nValue | null>(null)

function initialLocale(): Locale {
  try {
    const saved = localStorage.getItem(LOCALE_KEY)
    if (saved === 'pt-PT' || saved === 'en-GB') return saved
  } catch {
    /* storage unavailable */
  }
  return 'pt-PT' // the workbook and the business are Portuguese
}

export function I18nProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(initialLocale)

  const setLocale = useCallback((next: Locale) => {
    setLocaleState(next)
    try {
      localStorage.setItem(LOCALE_KEY, next)
    } catch {
      /* the choice just won't persist */
    }
  }, [])

  const value = useMemo<I18nValue>(() => {
    const dict = DICTS[locale]
    const t: TFn = (key, vars) => {
      let text = dict[key]
      if (vars) {
        for (const [name, v] of Object.entries(vars)) text = text.replaceAll(`{${name}}`, String(v))
      }
      return text
    }
    return { locale, setLocale, t }
  }, [locale, setLocale])

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>
}

export function useI18n(): I18nValue {
  const value = useContext(I18nContext)
  if (!value) throw new Error('useI18n must be used inside I18nProvider')
  return value
}

/** Message for a failed request, translated when it is a network failure. */
export function errorMessage(err: unknown, t: TFn, fallback: Key): string {
  if (err instanceof ApiError) return err.kind === 'network' ? t('errors.network') : err.message
  return t(fallback)
}

export function movementTypeLabel(t: TFn, type: MovementType | 'IMPORT'): string {
  return t(`type.${type}` as Key)
}

export function sourceLabel(t: TFn, source: Movement['source']): string {
  return t(`source.${source}` as Key)
}

export function formatDate(iso: string | null, locale: Locale): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleString(locale, { dateStyle: 'short', timeStyle: 'short' })
}
