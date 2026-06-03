const { app, BrowserWindow, screen, ipcMain } = require('electron')
const fs = require('fs')
const os = require('os')
const path = require('path')

const STATE_FILE = path.join(os.tmpdir(), 'vozdev_state.txt')
const SHOW_FILE  = path.join(os.tmpdir(), 'vozdev_show.txt')

  const W = 368
  const H = 61

let win

function getTargetDisplay() {
  const displays = screen.getAllDisplays()
  const internal = displays.find((d) => d.internal)
  return internal || screen.getPrimaryDisplay()
}

/**
 * MacBook Air/Pro (notch): Electron coloca la ventana en workArea (debajo del menú).
 * Subimos la ventana restando la altura de la barra de menú para quedar en la cámara.
 */
function getNotchPosition(width, height) {
  const { bounds, workArea } = getTargetDisplay()
  const menuBarH = Math.max(24, Math.round(workArea.y - bounds.y))
  const x = bounds.x + Math.round((bounds.width - width) / 2)
  const y =
    process.platform === 'darwin'
      ? bounds.y - menuBarH + 10
      : bounds.y
  return { x, y, menuBarH }
}

function placeInNotchArea(browserWin) {
  if (!browserWin || browserWin.isDestroyed()) return
  const [w, h] = browserWin.getSize()
  const { x, y } = getNotchPosition(w, h)
  const bounds = { x, y, width: w, height: h }
  browserWin.setBounds(bounds)
  // Apple Silicon / Sonoma: a veces ignora x,y al crear la ventana
  setImmediate(() => {
    if (!browserWin.isDestroyed()) browserWin.setBounds(bounds)
  })
}

app.whenReady().then(() => {
  const { x, y, menuBarH } = getNotchPosition(W, H)
  const isMac = process.platform === 'darwin'
  if (isMac) {
    console.log(`[voz widget] Mac notch: menuBar=${menuBarH}px → y=${y}`)
  }

  win = new BrowserWindow({
    width: W,
    height: H,
    x,
    y,
    frame: false,
    transparent: true,
    alwaysOnTop: true,
    hasShadow: false,
    resizable: false,
    skipTaskbar: true,
    show: false,
    fullscreenable: false,
    enableLargerThanScreen: isMac,
    ...(isMac
      ? {
          titleBarStyle: 'hidden',
          trafficLightPosition: { x: -100, y: -100 },
        }
      : {}),
    webPreferences: {
      nodeIntegration: true,
      contextIsolation: false,
    },
  })

  win.loadFile(path.join(__dirname, 'index.html'))
  win.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true })
  if (isMac) win.setAlwaysOnTop(true, 'status')

  const applyPosition = () => placeInNotchArea(win)

  win.once('ready-to-show', () => {
    applyPosition()
    win.show()
    applyPosition()
  })

  win.webContents.once('did-finish-load', applyPosition)

  screen.on('display-metrics-changed', applyPosition)

  app.setLoginItemSettings({ openAtLogin: true })

  // ── Polling show/hide ──
  setInterval(() => {
    try {
      const cmd = fs.readFileSync(SHOW_FILE, 'utf8').trim()
      if (cmd === 'show' && !win.isVisible()) {
        applyPosition()
        win.show()
        applyPosition()
        fs.writeFileSync(SHOW_FILE, 'shown')
      } else if (cmd === 'hide' && win.isVisible()) {
        win.hide()
        fs.writeFileSync(SHOW_FILE, 'hidden')
      }
    } catch (e) {}
  }, 100)

  // ── Polling state → renderer ──
  let lastState = ''
  setInterval(() => {
    try {
      const s = fs.readFileSync(STATE_FILE, 'utf8').trim()
      if (s && s !== lastState) {
        lastState = s
        if (win && !win.isDestroyed()) win.webContents.send('set-state', s)
      }
    } catch (e) {}
  }, 80)
})

app.on('window-all-closed', (e) => e.preventDefault())
