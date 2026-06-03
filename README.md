# voz-dev 🎙️

**Pair programming por voz en tu Mac.** Un agente de IA que vive en la barra superior, escucha cuando lo activas y ejecuta código, commits, búsquedas, capturas de pantalla y más — todo por voz, en español.

---

## Qué hace

- Hablas con `⌥A` (Option + A) desde cualquier app — sin tocar la terminal
- El agente escucha, entiende y actúa: edita archivos, hace commits, crea repos en GitHub, busca en la web, toma capturas de pantalla y las analiza
- Puedes interrumpirlo mientras habla (barge-in)
- Un widget flotante en el notch muestra el estado en tiempo real

---

## Requisitos

- macOS 13+
- Python 3.11+
- [PortAudio](https://formulae.brew.sh/formula/portaudio) — `brew install portaudio`
- API key de OpenAI con acceso a **GPT Realtime** (`gpt-realtime-2`)
- `gh` CLI (para herramientas de GitHub) — `brew install gh` → `gh auth login`

---

## Instalación

```bash
git clone https://github.com/tu-usuario/voz-dev.git
cd voz-dev

# Crear venv e instalar dependencias
python3 -m venv venv
venv/bin/pip install -r requirements.txt

# Configurar credenciales
cp .env.example .env
# Edita .env y añade tu OPENAI_API_KEY
```

**Instalar como servicio (arranca al encender el Mac):**

```bash
./dev.sh install
```

---

## Uso

| Comando | Qué hace |
|---|---|
| `./dev.sh install` | Instala el agente como LaunchAgent — arranca solo |
| `./dev.sh now` | Sesión de voz inmediata sin instalar como servicio |
| `./dev.sh now /ruta/proyecto` | Sesión apuntando a un proyecto específico |
| `./dev.sh stop` | Detiene el agente y el widget |
| `./dev.sh logs` | Muestra logs en tiempo real |
| `./dev.sh status` | Estado del servicio |
| `./dev.sh uninstall` | Desinstala el LaunchAgent |

Una vez activo, usa **`⌥A`** desde cualquier aplicación para abrir una sesión de voz.

---

## Configuración (`.env`)

```env
OPENAI_API_KEY=sk-...

# Activación
VOZ_ACTIVATION=hotkey        # hotkey | always | wake
VOZ_HOTKEY_KEYS=option+a
VOZ_GREET_ON_ACTIVATE=1      # saludo al activar

# Voz
VOZ_VOICE=cedar              # alloy | ash | ballad | coral | echo | sage | shimmer | verse | cedar
VOZ_GREETING_MESSAGE=        # mensaje personalizado al activar (opcional)

# Audio
VOZ_VAD_THRESHOLD=0.38       # sensibilidad del detector de voz (0.1 – 0.9)
VOZ_MIC_GAIN=1.5             # ganancia del micrófono
VOZ_NOISE_REDUCTION=far_field  # off | near_field | far_field
VOZ_HALF_DUPLEX=1            # silencia el mic mientras habla el agente (anti-eco)

# Barge-in — interrumpir al agente mientras habla
VOZ_ALLOW_BARGE_IN=1
VOZ_INTERRUPT_RESPONSE=1

# Herramientas activas
VOZ_TOOL_GROUPS=coding,ide,git,mac,web,vision,notes

# Notas
VOZ_NOTES_DIR=~/Documents/VozNotas

# Visión
VOZ_VISION_MODEL=gpt-4o-mini

# Proyecto por defecto
VOZ_PROJECT_ROOT=~/Desktop/mi-proyecto
```

---

## Herramientas disponibles

### Código & IDE
| Lo que dices | Qué hace |
|---|---|
| "Revisa main.py" | Lee y analiza el archivo |
| "Edita la función X para que haga Y" | Edita el archivo directamente |
| "Ejecuta los tests" | Corre la suite de tests |
| "Abre el archivo en Cursor" | Abre en el editor |
| "Copia el resultado al portapapeles" | `escribir_clipboard` |

### Git & GitHub
| Lo que dices | Qué hace |
|---|---|
| "Haz commit con mensaje X" | `git add -A && git commit` |
| "Súbelo a GitHub" | commit + push en un paso |
| "Crea una rama llamada feature/login" | `git checkout -b` |
| "Crea un repositorio para este proyecto" | `gh repo create` + push |
| "Inicializa git y súbelo a GitHub" | init → commit → crea repo → push |
| "Lista mis repos" | `gh repo list` |
| "Clona el repo X" | `gh repo clone` |
| "Crea un PR" | `gh pr create` |
| "Haz pull" | `git pull` |
| "Guarda los cambios en stash" | `git stash` |

### Web
| Lo que dices | Qué hace |
|---|---|
| "Busca cómo funciona X" | Búsqueda web + respuesta |
| "Investiga sobre X" | Búsqueda profunda con fuentes |

### Visión (pantalla)
| Lo que dices | Qué hace |
|---|---|
| "Qué ves en pantalla" | Captura + análisis con GPT-4o Vision |
| "Lee el error que aparece" | Transcribe el error visible |
| "Mira la UI" | Describe elementos en pantalla |

Al tomar una captura, aparece un **borde verde** alrededor de la ventana activa como confirmación visual.

### Notas
| Lo que dices | Qué hace |
|---|---|
| "Anota que..." | Crea nota en `~/Documents/VozNotas/` |
| "Agrega a la nota X esto..." | Añade texto al final |
| "Lee la nota X" | Lee el contenido |
| "Qué notas tengo" | Lista con fechas |
| "Busca en mis notas X" | Búsqueda en todos los archivos |
| "Crea nota en Apple Notes" | Crea en la app Notas nativa |

### Mac
| Lo que dices | Qué hace |
|---|---|
| "Abre Spotify" | Abre la app |
| "Pon X en Spotify" | Reproduce canción/playlist |
| "Avísame cuando termine" | Notificación macOS |
| "Qué tengo copiado" | Lee el portapapeles |
| "Crea el proyecto X en el escritorio" | Scaffolding de proyecto |

---

## Arquitectura

```
voz-dev/
├── main.py                    # Punto de entrada
├── voz/
│   ├── app.py                 # Lógica principal (hotkey, wake, always)
│   ├── realtime.py            # WebSocket con OpenAI Realtime API
│   ├── audio.py               # Captura, resample, ganancia, barge-in
│   ├── config.py              # Variables de entorno
│   ├── prompts.py             # System prompt del agente
│   ├── hotkey.py              # Listener de atajo de teclado
│   ├── wake.py                # Wake word (modo alternativo)
│   ├── widget_ctl.py          # Control del widget flotante
│   ├── screen_flash.py        # Borde verde al tomar capturas
│   └── menubar.py             # Ícono en la barra de menú (macOS)
├── widget.py                  # Widget flotante (pywebview)
├── widget-electron/
│   └── index.html             # UI del widget (HTML/CSS/JS)
├── agent_tools/
│   ├── handlers/
│   │   ├── ide.py             # Leer, editar, buscar código
│   │   ├── git.py             # Git (commit, push, PR, issues)
│   │   ├── github.py          # Repos, clonar, ramas, stash, merge
│   │   ├── patch.py           # Aplicar patches, escribir archivos
│   │   ├── vision.py          # Captura de pantalla + análisis
│   │   ├── web.py             # Búsqueda web
│   │   ├── mac.py             # Apps, Spotify, portapapeles, notas
│   │   └── notes.py           # Sistema de notas en markdown
│   ├── plugins.py             # Cargador de plugins externos
│   ├── registry.py            # Registro de herramientas
│   └── context.py             # Contexto compartido entre tools
├── dev.sh                     # CLI de gestión del servicio
└── scripts/
    └── macos-install.sh       # Instalación como LaunchAgent
```

---

## Plugins

Puedes añadir herramientas propias en `~/.voz/tools/`. Cada archivo `.py` debe exportar una función `register_tools()`:

```python
# ~/.voz/tools/mi_tool.py
from agent_tools.registry import ToolSpec, register

def register_tools():
    register(ToolSpec(
        name="mi_herramienta",
        description="Hace X cuando el usuario pide Y",
        parameters={"type": "object", "properties": {}, "required": []},
        handler=lambda args, ctx: "resultado",
        category="coding",
    ))
```

El directorio de plugins es configurable con `VOZ_PLUGINS_DIR`.

---

## Permisos macOS necesarios

La primera vez macOS pedirá autorización para:

- **Micrófono** — para escuchar tu voz
- **Accesibilidad** — para el atajo global `⌥A`
- **Grabación de pantalla** — para `ver_pantalla` / capturas

Ve a **Ajustes del Sistema → Privacidad y Seguridad** para habilitarlos.

---

## Requisitos de sistema

| Componente | Mínimo |
|---|---|
| macOS | 13 Ventura |
| Python | 3.11 |
| RAM | 4 GB |
| Red | Requerida (streaming a OpenAI) |
| API | OpenAI con acceso a GPT Realtime |

---

## Licencia

MIT
