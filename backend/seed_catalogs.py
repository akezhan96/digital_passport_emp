"""Bulk reference data: countries, and the requirement-type form specs."""

# ---------------------------------------------------------------------------
# Countries  (code, ru, kk, en)
# ---------------------------------------------------------------------------

COUNTRIES = [
    # Central Asia & CIS
    ("KZ", "Казахстан", "Қазақстан", "Kazakhstan"),
    ("RU", "Россия", "Ресей", "Russia"),
    ("UZ", "Узбекистан", "Өзбекстан", "Uzbekistan"),
    ("KG", "Кыргызстан", "Қырғызстан", "Kyrgyzstan"),
    ("TJ", "Таджикистан", "Тәжікстан", "Tajikistan"),
    ("TM", "Туркменистан", "Түрікменстан", "Turkmenistan"),
    ("AZ", "Азербайджан", "Әзербайжан", "Azerbaijan"),
    ("AM", "Армения", "Армения", "Armenia"),
    ("GE", "Грузия", "Грузия", "Georgia"),
    ("BY", "Беларусь", "Беларусь", "Belarus"),
    ("UA", "Украина", "Украина", "Ukraine"),
    ("MD", "Молдова", "Молдова", "Moldova"),
    ("MN", "Монголия", "Моңғолия", "Mongolia"),

    # Europe
    ("AT", "Австрия", "Австрия", "Austria"),
    ("DE", "Германия", "Германия", "Germany"),
    ("FR", "Франция", "Франция", "France"),
    ("GB", "Великобритания", "Ұлыбритания", "United Kingdom"),
    ("IE", "Ирландия", "Ирландия", "Ireland"),
    ("NL", "Нидерланды", "Нидерланд", "Netherlands"),
    ("BE", "Бельгия", "Бельгия", "Belgium"),
    ("LU", "Люксембург", "Люксембург", "Luxembourg"),
    ("CH", "Швейцария", "Швейцария", "Switzerland"),
    ("IT", "Италия", "Италия", "Italy"),
    ("ES", "Испания", "Испания", "Spain"),
    ("PT", "Португалия", "Португалия", "Portugal"),
    ("GR", "Греция", "Грекия", "Greece"),
    ("PL", "Польша", "Польша", "Poland"),
    ("CZ", "Чехия", "Чехия", "Czechia"),
    ("SK", "Словакия", "Словакия", "Slovakia"),
    ("HU", "Венгрия", "Венгрия", "Hungary"),
    ("RO", "Румыния", "Румыния", "Romania"),
    ("BG", "Болгария", "Болгария", "Bulgaria"),
    ("HR", "Хорватия", "Хорватия", "Croatia"),
    ("SI", "Словения", "Словения", "Slovenia"),
    ("RS", "Сербия", "Сербия", "Serbia"),
    ("SE", "Швеция", "Швеция", "Sweden"),
    ("NO", "Норвегия", "Норвегия", "Norway"),
    ("FI", "Финляндия", "Финляндия", "Finland"),
    ("DK", "Дания", "Дания", "Denmark"),
    ("IS", "Исландия", "Исландия", "Iceland"),
    ("EE", "Эстония", "Эстония", "Estonia"),
    ("LV", "Латвия", "Латвия", "Latvia"),
    ("LT", "Литва", "Литва", "Lithuania"),
    ("CY", "Кипр", "Кипр", "Cyprus"),
    ("MT", "Мальта", "Мальта", "Malta"),

    # Middle East
    ("TR", "Турция", "Түркия", "Turkey"),
    ("AE", "ОАЭ", "БАӘ", "United Arab Emirates"),
    ("SA", "Саудовская Аравия", "Сауд Арабиясы", "Saudi Arabia"),
    ("QA", "Катар", "Катар", "Qatar"),
    ("KW", "Кувейт", "Кувейт", "Kuwait"),
    ("BH", "Бахрейн", "Бахрейн", "Bahrain"),
    ("OM", "Оман", "Оман", "Oman"),
    ("IL", "Израиль", "Израиль", "Israel"),
    ("JO", "Иордания", "Иордания", "Jordan"),
    ("IR", "Иран", "Иран", "Iran"),
    ("IQ", "Ирак", "Ирак", "Iraq"),

    # Asia
    ("CN", "Китай", "Қытай", "China"),
    ("JP", "Япония", "Жапония", "Japan"),
    ("KR", "Республика Корея", "Корея Республикасы", "South Korea"),
    ("IN", "Индия", "Үндістан", "India"),
    ("PK", "Пакистан", "Пәкістан", "Pakistan"),
    ("BD", "Бангладеш", "Бангладеш", "Bangladesh"),
    ("SG", "Сингапур", "Сингапур", "Singapore"),
    ("MY", "Малайзия", "Малайзия", "Malaysia"),
    ("ID", "Индонезия", "Индонезия", "Indonesia"),
    ("TH", "Таиланд", "Тайланд", "Thailand"),
    ("VN", "Вьетнам", "Вьетнам", "Vietnam"),
    ("PH", "Филиппины", "Филиппин", "Philippines"),
    ("HK", "Гонконг", "Гонконг", "Hong Kong"),
    ("TW", "Тайвань", "Тайвань", "Taiwan"),
    ("AF", "Афганистан", "Ауғанстан", "Afghanistan"),

    # Americas
    ("US", "США", "АҚШ", "United States"),
    ("CA", "Канада", "Канада", "Canada"),
    ("MX", "Мексика", "Мексика", "Mexico"),
    ("BR", "Бразилия", "Бразилия", "Brazil"),
    ("AR", "Аргентина", "Аргентина", "Argentina"),
    ("CL", "Чили", "Чили", "Chile"),
    ("CO", "Колумбия", "Колумбия", "Colombia"),
    ("PE", "Перу", "Перу", "Peru"),

    # Africa & Oceania
    ("EG", "Египет", "Мысыр", "Egypt"),
    ("MA", "Марокко", "Марокко", "Morocco"),
    ("DZ", "Алжир", "Алжир", "Algeria"),
    ("TN", "Тунис", "Тунис", "Tunisia"),
    ("ZA", "ЮАР", "ОАР", "South Africa"),
    ("NG", "Нигерия", "Нигерия", "Nigeria"),
    ("KE", "Кения", "Кения", "Kenya"),
    ("ET", "Эфиопия", "Эфиопия", "Ethiopia"),
    ("AU", "Австралия", "Австралия", "Australia"),
    ("NZ", "Новая Зеландия", "Жаңа Зеландия", "New Zealand"),
]


# ---------------------------------------------------------------------------
# Requirement types
#
# `condition_schema` is a FORM SPECIFICATION the UI renders into real inputs.
# Field kinds:
#   number  -- numeric input (min / step / suffix)
#   ref     -- dropdown fed from a reference catalogue; `value_field` says
#              which column is stored in the condition (always "code" here)
#   boolean -- checkbox
#   list    -- repeatable group of `item_fields`, stored as an array
# ---------------------------------------------------------------------------

def _years(key="min_years", ru="Минимальный стаж", kk="Ең аз өтіл",
           en="Minimum experience", required=True):
    return {
        "key": key, "kind": "number", "required": required,
        "label_ru": ru, "label_kk": kk, "label_en": en,
        "min": 0, "step": 0.5, "default": 0,
        "suffix_ru": "лет", "suffix_kk": "жыл", "suffix_en": "years",
    }


def _ref(key, catalog, ru, kk, en, required=True):
    return {
        "key": key, "kind": "ref", "catalog": catalog, "value_field": "code",
        "required": required, "label_ru": ru, "label_kk": kk, "label_en": en,
    }


REQUIREMENT_TYPES = [
    ("COMPANY_TENURE", "Стаж в компании", "Компаниядағы өтіл", "Company tenure",
     "company_tenure", {
         "hint_ru": "Сколько лет сотрудник должен проработать в компании.",
         "hint_kk": "Қызметкер компанияда неше жыл жұмыс істеуі керек.",
         "hint_en": "How many years the employee must have worked at the company.",
         "fields": [_years()],
     }),

    ("TOTAL_EXPERIENCE", "Общий стаж", "Жалпы өтіл", "Total experience",
     "total_experience", {
         "hint_ru": "Общий трудовой стаж, включая прежних работодателей.",
         "hint_kk": "Бұрынғы жұмыс берушілерді қоса алғандағы жалпы өтіл.",
         "hint_en": "Total working experience, including previous employers.",
         "fields": [_years()],
     }),

    ("FUNCTION_EXPERIENCE", "Опыт по профессиональной функции",
     "Кәсіби функция бойынша тәжірибе", "Functional experience",
     "function_experience", {
         "hint_ru": "Опыт считается по профессиональной функции, а не по "
                    "названию должности.",
         "hint_kk": "Тәжірибе лауазым атауы бойынша емес, кәсіби функция "
                    "бойынша есептеледі.",
         "hint_en": "Experience is counted by professional function, not by "
                    "job title.",
         "fields": [
             _ref("job_family_code", "job-families",
                  "Профессиональная функция", "Кәсіби функция", "Job family"),
             _years(),
         ],
     }),

    ("LANGUAGE", "Знание языка", "Тіл білу", "Language", "language", {
        "hint_ru": "Достаточно выполнить любую строку из списка.",
        "hint_kk": "Тізімдегі кез келген жолды орындау жеткілікті.",
        "hint_en": "Satisfying any one row in the list is enough.",
        "fields": [{
            "key": "any_of", "kind": "list", "required": True,
            "label_ru": "Допустимые языки (любой из)",
            "label_kk": "Рұқсат етілген тілдер (кез келгені)",
            "label_en": "Accepted languages (any of)",
            "add_ru": "Добавить язык", "add_kk": "Тіл қосу",
            "add_en": "Add language",
            "min_items": 1,
            "item_fields": [
                _ref("language_code", "languages", "Язык", "Тіл", "Language"),
                _ref("min_level", "language-levels",
                     "Минимальный уровень", "Ең төменгі деңгей", "Minimum level"),
                {"key": "confirmed", "kind": "boolean", "default": True,
                 "label_ru": "Только подтверждённый документом",
                 "label_kk": "Тек құжатпен расталған",
                 "label_en": "Confirmed by a document only"},
            ],
        }],
    }),

    ("ORG_UNIT_EXPERIENCE", "Опыт в типе подразделения",
     "Бөлімше түріндегі тәжірибе", "Org-unit experience",
     "org_unit_experience", {
         "hint_ru": "Оставьте 0 лет, чтобы требовать только факт наличия опыта.",
         "hint_kk": "Тек тәжірибенің болуын талап ету үшін 0 жыл қалдырыңыз.",
         "hint_en": "Leave 0 years to require merely that such experience exists.",
         "fields": [
             _ref("org_unit_type_code", "org-unit-types",
                  "Тип подразделения", "Бөлімше түрі", "Unit type"),
             _years(required=False),
         ],
     }),

    ("COUNTRY_EXPERIENCE", "Опыт работы в стране", "Елдегі жұмыс тәжірибесі",
     "Country experience", "country_experience", {
         "hint_ru": "Оставьте 0 лет, чтобы требовать только факт наличия опыта.",
         "hint_kk": "Тек тәжірибенің болуын талап ету үшін 0 жыл қалдырыңыз.",
         "hint_en": "Leave 0 years to require merely that such experience exists.",
         "fields": [
             _ref("country_code", "countries", "Страна", "Ел", "Country"),
             _years(required=False),
         ],
     }),

    ("COMPETENCY", "Компетенция", "Құзыреттілік", "Competency", "competency", {
        "hint_ru": "Балл берётся из последней проведённой оценки.",
        "hint_kk": "Ұпай соңғы бағалаудан алынады.",
        "hint_en": "The score is taken from the most recent assessment.",
        "fields": [
            _ref("competency_code", "competencies",
                 "Компетенция", "Құзыреттілік", "Competency"),
            {"key": "min_score", "kind": "number", "required": True,
             "label_ru": "Минимальный балл", "label_kk": "Ең төменгі ұпай",
             "label_en": "Minimum score", "min": 0, "step": 0.1, "default": 3.5},
        ],
    }),

    ("EDUCATION", "Образование", "Білім", "Education", "education", {
        "hint_ru": "Можно указать только уровень, только специальность или оба.",
        "hint_kk": "Тек деңгейді, тек мамандықты немесе екеуін де көрсетуге болады.",
        "hint_en": "You may set only the level, only the field, or both.",
        "fields": [
            _ref("min_level_code", "education-levels",
                 "Уровень образования", "Білім деңгейі", "Education level",
                 required=False),
            _ref("field_code", "education-fields",
                 "Специальность", "Мамандық", "Field of study", required=False),
        ],
    }),

    ("TRAINING", "Обучение / курсы", "Оқыту / курстар", "Training", "training", {
        "hint_ru": "Оставьте 0 месяцев, чтобы срок давности не учитывался.",
        "hint_kk": "Ескіру мерзімі ескерілмеуі үшін 0 ай қалдырыңыз.",
        "hint_en": "Leave 0 months to ignore how recent the course was.",
        "fields": [
            _ref("job_family_code", "job-families",
                 "Направление обучения", "Оқыту бағыты", "Discipline"),
            {"key": "within_months", "kind": "number", "required": False,
             "label_ru": "Пройдено не ранее чем", "label_kk": "Өткізілген мерзімі",
             "label_en": "Completed within the last",
             "min": 0, "step": 1, "default": 0,
             "suffix_ru": "мес.", "suffix_kk": "ай", "suffix_en": "months"},
        ],
    }),
]
