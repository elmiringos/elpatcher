# Отчёт: Patcher - AI Code Agent

## 1. Обзор проекта

**Patcher** — это AI-агент для автоматизации жизненного цикла разработки ПО (SDLC) на GitHub. Агент автоматически обрабатывает issues, генерирует код, создаёт pull requests и проводит code review.

---

## 2. Используемые инструменты и технологии

### 2.1 Языки и фреймворки

| Технология | Версия | Назначение |
|------------|--------|------------|
| Python | 3.11+ | Основной язык |
| FastAPI | 0.109+ | Webhook сервер и REST API |
| Uvicorn | 0.27+ | ASGI сервер |
| Pydantic | 2.5+ | Валидация данных и схемы |

### 2.2 LLM экосистема

| Библиотека | Назначение |
|------------|------------|
| LangChain | Оркестрация LLM вызовов |
| LangChain-OpenAI | Интеграция с OpenAI GPT |
| LangChain-Anthropic | Интеграция с Claude |
| LangGraph | Построение агентных графов с состоянием |

### 2.3 GitHub интеграция

| Библиотека | Назначение |
|------------|------------|
| PyGithub | GitHub REST API клиент |
| GitPython | Локальные Git операции |
| PyJWT | JWT токены для GitHub App |

### 2.4 Дополнительные инструменты

| Инструмент | Назначение |
|------------|------------|
| httpx | Асинхронный HTTP клиент |
| tree-sitter | Парсинг кода (опционально) |
| Docker | Контейнеризация |

---

## 3. Архитектура системы

### 3.1 Общая схема

```
┌─────────────────────────────────────────────────────────────┐
│                        GitHub                                │
│  ┌─────────┐    ┌─────────┐    ┌─────────┐                  │
│  │  Issue  │    │   PR    │    │   CI    │                  │
│  └────┬────┘    └────┬────┘    └────┬────┘                  │
└───────┼──────────────┼──────────────┼───────────────────────┘
        │              │              │
        ▼              ▼              ▼
┌─────────────────────────────────────────────────────────────┐
│                    Webhook Server                            │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  FastAPI App (app.py)                                 │   │
│  │  ├── POST /webhook    - GitHub webhooks               │   │
│  │  ├── POST /api/review - Синхронный review API         │   │
│  │  └── GET /health      - Health check                  │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────────┐
│                    Webhook Handlers                          │
│  ┌────────────────┐  ┌────────────────┐  ┌───────────────┐  │
│  │ handle_issue   │  │ handle_pr      │  │ handle_comment│  │
│  │ (issues/opened)│  │ (pr/opened)    │  │ (@patcher fix)│  │
│  └───────┬────────┘  └───────┬────────┘  └───────┬───────┘  │
└──────────┼───────────────────┼───────────────────┼──────────┘
           │                   │                   │
           ▼                   ▼                   ▼
┌─────────────────────────────────────────────────────────────┐
│                        Agents                                │
│  ┌─────────────────────────┐  ┌─────────────────────────┐   │
│  │      CodeAgent          │  │     ReviewAgent         │   │
│  │  ├── Анализ issue       │  │  ├── Анализ PR diff     │   │
│  │  ├── Исследование кода  │  │  ├── Проверка issue     │   │
│  │  ├── Генерация кода     │  │  ├── CI анализ          │   │
│  │  ├── Создание PR        │  │  └── Публикация review  │   │
│  │  └── Итерации по review │  │                         │   │
│  └─────────────────────────┘  └─────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
           │                   │
           ▼                   ▼
┌─────────────────────────────────────────────────────────────┐
│                     LLM Provider                             │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Structured Output Chains (Pydantic schemas)          │   │
│  │  ├── CodeGeneration  - генерация файлов              │   │
│  │  ├── CodeReview      - результат review              │   │
│  │  └── CIAnalysis      - анализ CI ошибок              │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 Структура модулей

```
src/patcher/
├── agents/                 # AI агенты
│   ├── base.py            # Базовый класс агента
│   ├── code_agent.py      # Агент генерации кода
│   ├── review_agent.py    # Агент code review
│   ├── graph_agent.py     # LangGraph агент
│   └── tools.py           # Инструменты для агентов
│
├── server/                 # Webhook сервер
│   ├── app.py             # FastAPI приложение
│   ├── webhooks.py        # Обработчики webhook
│   ├── api.py             # REST API endpoints
│   ├── github_app.py      # GitHub App аутентификация
│   └── config.py          # Конфигурация
│
├── github/                 # GitHub клиент
│   ├── client.py          # Обёртка над PyGithub
│   └── models.py          # Pydantic модели
│
├── llm/                    # LLM интеграция
│   ├── provider.py        # LLM провайдер
│   ├── factory.py         # Фабрика провайдеров
│   └── schemas.py         # Pydantic схемы для structured output
│
├── code/                   # Анализ кода
│   ├── analyzer.py        # Анализатор кодовой базы
│   ├── repo_map.py        # Карта репозитория
│   └── search.py          # Поиск по коду
│
├── prompts/                # Промпты
│   ├── few_shots.py       # Few-shot примеры
│   └── templates.py       # Шаблоны промптов
│
└── state/                  # Управление состоянием
    ├── manager.py         # Менеджер состояния
    └── models.py          # Модели состояния
```

---

## 4. Промпт-техники

### 4.1 Structured Output (Структурированный вывод)

Используем Pydantic схемы для гарантированного формата ответа LLM:

```python
class CodeGeneration(BaseModel):
    files: list[FileChange]
    explanation: str

class CodeReview(BaseModel):
    assessment: str
    issues: list[ReviewIssue]
    requirements_met: bool
    approved: bool
```

**Преимущества:**
- Валидация ответа на уровне типов
- Автоматический retry при ошибке парсинга
- Детерминированный формат для downstream обработки

### 4.2 Few-Shot Learning (Обучение на примерах)

Добавляем примеры ожидаемого input/output в промпт:

```python
CODE_GENERATION_EXAMPLES = [
    {
        "issue": "Add email validation function",
        "output": '{"files": [{"path": "src/validators.py", ...}]}'
    },
]
```

**Категории примеров:**
| Категория | Количество | Назначение |
|-----------|------------|------------|
| CODE_GENERATION | 2 | Генерация кода по issue |
| CODE_FIX | 2 | Исправления по review |
| CI_FIX | 3 | Исправления CI ошибок |
| REVIEW | 3 | Code review (approve/reject) |

### 4.3 Role-Based Prompting (Ролевые промпты)

Задаём роль и контекст в system prompt:

```python
SYSTEM_PROMPT = """You are a strict code reviewer.
Your PRIMARY task is to verify that the PR solves the related issue.

Guidelines:
1. MAIN CRITERION: Does the implementation solve the issue requirements?
2. Only report issues that BLOCK the issue from being solved
3. DO NOT report style suggestions...
"""
```

### 4.4 Chain-of-Thought (Цепочка рассуждений)

Структурированные шаги в промпте:

```
STRICT REVIEW CRITERIA:
1. Does this PR FULLY solve the issue requirements?
2. Are there any CRITICAL bugs?
3. Are there any SECURITY vulnerabilities?
```

### 4.5 Constraint-Based Prompting (Ограничения)

Явные запреты и ограничения:

```
DO NOT REPORT:
- Style suggestions
- Performance optimizations (unless critical)
- "Nice to have" improvements

IMPORTANT: Only fix what's needed to pass CI. Don't refactor.
```

---

## 5. Workflow агентов

### 5.1 CodeAgent - обработка issue

```
1. Получение issue из GitHub
2. Клонирование репозитория
3. Анализ кодовой базы (LangGraph + tools)
   ├── detect_languages
   ├── get_repository_map
   ├── read_file
   ├── search_code
   └── find_definition
4. Генерация кода (Structured Output)
5. Создание branch и commit
6. Создание Pull Request
7. [Итерация] Обработка review feedback
```

### 5.2 ReviewAgent - code review

```
1. Получение PR и diff
2. Извлечение связанной issue
3. Анализ CI статуса
4. Анализ diff против issue (Few-shot + Structured Output)
5. Генерация review
6. Публикация review в GitHub
```

---

## 6. Защитные механизмы

### 6.1 Дедупликация обработки

```python
# Предотвращение двойной обработки issue/PR
_processing_issues: dict[str, bool] = {}
_reviewing_prs: dict[str, bool] = {}

def mark_issue_processing(repo, issue_number) -> bool:
    # Returns False if already processing
```

### 6.2 Ограничение итераций

```python
MAX_ITERATIONS = 3  # Максимум попыток исправления
```

### 6.3 Запрет изменения CI/CD

```python
IMPORTANT RESTRICTIONS:
- NEVER create or modify GitHub Actions workflow files
- NEVER create or modify CI/CD configuration files
```

---

## 7. Конфигурация

### Переменные окружения

| Переменная | Описание |
|------------|----------|
| `GITHUB_APP_ID` | ID GitHub App |
| `GITHUB_PRIVATE_KEY` | Приватный ключ GitHub App |
| `GITHUB_WEBHOOK_SECRET` | Секрет для верификации webhook |
| `OPENAI_API_KEY` | API ключ OpenAI |
| `ANTHROPIC_API_KEY` | API ключ Anthropic |
| `LLM_PROVIDER` | Провайдер LLM (openai/anthropic) |
| `MAX_ITERATIONS` | Максимум итераций исправления |

---

## 8. Развёртывание

### Docker Compose

```yaml
services:
  patcher-server:
    build: .
    ports:
      - "8080:8080"
    environment:
      - GITHUB_APP_ID=${GITHUB_APP_ID}
      - GITHUB_PRIVATE_KEY=${GITHUB_PRIVATE_KEY}
      - OPENAI_API_KEY=${OPENAI_API_KEY}
```

### GitHub App Permissions

| Permission | Access | Назначение |
|------------|--------|------------|
| Issues | Read & Write | Чтение issues, комментарии |
| Pull Requests | Read & Write | Создание PR, review |
| Contents | Read & Write | Чтение/запись файлов |
| Checks | Read | Статус CI |

---

## 9. Заключение

Patcher демонстрирует современный подход к созданию AI-агентов для автоматизации разработки:

- **LangChain/LangGraph** для оркестрации LLM
- **Structured Output** для надёжного парсинга
- **Few-Shot Learning** для улучшения качества генерации
- **GitHub App** для безопасной интеграции
- **Асинхронная архитектура** для масштабируемости
