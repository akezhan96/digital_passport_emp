const ru = {
  summary: 'Кадровые показатели', asOf: 'На', current: 'Текущее положение', disposal: 'В распоряжении',
  total: 'Общий стаж', company: 'В организации', tenureNote: 'Периоды в распоряжении исключены из стажа.',
  noData: 'Нет сведений', day: 'дн.', since: 'С', onPost: 'На должности с', appointed: 'Назначен с',
  contract: 'Контракт', rank: 'Звание', recognition: 'Поощрение', indefinite: 'Бессрочный',
  signed: 'Подписан', expiry: 'Действует до', unknownEnd: 'Срок окончания не указан',
  remaining: 'Осталось', overdue: 'Срок истёк', today: 'Истекает сегодня',
  received: 'Присвоено', rewarded: 'Последнее поощрение', elapsed: 'Прошло', planned: 'Следующее присвоение',
  due: 'До плановой даты', dueToday: 'Плановая дата сегодня', past: 'После плановой даты',
  records: 'Контракты, звания и поощрения', empty: 'Кадровых записей пока нет.',
  add: 'Добавить запись', edit: 'Редактировать запись', type: 'Вид записи',
  contractTitle: 'Название контракта (необязательно)', rankTitle: 'Название звания', recognitionTitle: 'Вид поощрения',
  contractDate: 'Дата подписания', rankDate: 'Дата присвоения', recognitionDate: 'Дата поощрения',
  endDate: 'Дата окончания', plannedDate: 'Плановая дата следующего присвоения',
  undo: 'Отменить вывод', undoQuestion: 'Отменить вывод в распоряжение с {date} и восстановить предыдущее состояние?',
  deleteQuestion: 'Удалить запись «{name}» от {date} из личного дела?', manual: 'Период работы', origin: 'Прежнее подразделение',
  disposalHint: 'Период учитывается отдельно от стажа. Следующее назначение завершит его.',
  saved: 'Кадровая запись сохранена', removed: 'Кадровая запись удалена',
}
const kk = {
  summary: 'Кадрлық көрсеткіштер', asOf: 'Есеп күні', current: 'Ағымдағы мәртебе', disposal: 'Қарамағында',
  total: 'Жалпы еңбек өтілі', company: 'Ұйымдағы өтіл', tenureNote: 'Қарамағында болған кезеңдер еңбек өтіліне кірмейді.',
  noData: 'Дерек жоқ', day: 'күн', since: 'Басталған күні', onPost: 'Лауазымда жұмыс істеген күні', appointed: 'Тағайындалған күні',
  contract: 'Келісімшарт', rank: 'Атақ', recognition: 'Көтермелеу', indefinite: 'Мерзімсіз',
  signed: 'Қол қойылған күні', expiry: 'Аяқталатын күні', unknownEnd: 'Аяқталу күні көрсетілмеген',
  remaining: 'Қалғаны', overdue: 'Мерзімі аяқталды', today: 'Бүгін аяқталады',
  received: 'Берілген күні', rewarded: 'Соңғы көтермелеу', elapsed: 'Өткен уақыт', planned: 'Келесі атақ беру',
  due: 'Жоспарлы күнге дейін', dueToday: 'Жоспарлы күн бүгін', past: 'Жоспарлы күннен бері',
  records: 'Келісімшарттар, атақтар және көтермелеулер', empty: 'Кадрлық жазбалар әзірге жоқ.',
  add: 'Жазба қосу', edit: 'Жазбаны өзгерту', type: 'Жазба түрі',
  contractTitle: 'Келісімшарт атауы (міндетті емес)', rankTitle: 'Атақ атауы', recognitionTitle: 'Көтермелеу түрі',
  contractDate: 'Қол қойылған күні', rankDate: 'Атақ берілген күні', recognitionDate: 'Көтермелеу күні',
  endDate: 'Аяқталу күні', plannedDate: 'Келесі атақты берудің жоспарлы күні',
  undo: 'Қарамағына шығаруды болдырмау', undoQuestion: '{date} күнінен бастап қарамағына шығару жойылып, алдыңғы күй қалпына келтірілсін бе?',
  deleteQuestion: 'Жеке істен {date} күнгі «{name}» жазбасы жойылсын ба?', manual: 'Жұмыс кезеңі', origin: 'Алдыңғы бөлімше',
  disposalHint: 'Бұл кезең еңбек өтілінен бөлек есептеледі. Келесі тағайындау осы кезеңді аяқтайды.',
  saved: 'Кадрлық жазба сақталды', removed: 'Кадрлық жазба жойылды',
}
export const personnelText = lang => lang === 'kk' ? kk : ru
export function dateLabel(iso) {
  if (!iso) return '—'
  const parts = iso.split('-')
  return parts.length === 3 ? parts.reverse().join('.') : iso
}
export function dayCount(days, lang) {
  if (days == null) return personnelText(lang).noData
  return new Intl.NumberFormat(lang === 'kk' ? 'kk-KZ' : 'ru-RU').format(days) + ' ' + personnelText(lang).day
}
export function localToday() {
  const now = new Date()
  return [now.getFullYear(), String(now.getMonth() + 1).padStart(2, '0'), String(now.getDate()).padStart(2, '0')].join('-')
}
