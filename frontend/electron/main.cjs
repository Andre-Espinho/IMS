// Electron main process: starts the Python backend, then opens the UI window.
const { app, BrowserWindow, dialog } = require('electron')
const { spawn } = require('node:child_process')
const path = require('node:path')

const REPO_ROOT = path.resolve(__dirname, '..', '..')
const BACKEND_DIR = path.join(REPO_ROOT, 'backend')
// Override with IMS_PYTHON if the venv lives elsewhere.
const PYTHON = process.env.IMS_PYTHON || path.join(BACKEND_DIR, '.venv', 'Scripts', 'python.exe')
const BACKEND_PORT = 8000
const DEV_URL = 'http://localhost:5173'

let backend = null
let quitting = false
const recentOutput = [] // last lines of backend output, shown if it crashes

function remember(line) {
  console.log('[backend]', line)
  recentOutput.push(line)
  if (recentOutput.length > 30) recentOutput.shift()
}

function startBackend() {
  backend = spawn(
    PYTHON,
    ['-m', 'uvicorn', 'ims.main:app', '--host', '127.0.0.1', '--port', String(BACKEND_PORT)],
    {
      cwd: BACKEND_DIR,
      env: { ...process.env, PYTHONPATH: BACKEND_DIR, PYTHONIOENCODING: 'utf-8' },
      windowsHide: true,
    },
  )
  backend.stdout.on('data', (d) => d.toString().trimEnd().split('\n').forEach(remember))
  backend.stderr.on('data', (d) => d.toString().trimEnd().split('\n').forEach(remember))
  backend.on('error', (err) => {
    dialog.showErrorBox('IMS', `Não foi possível iniciar o servidor:\n${err.message}\n\nPython: ${PYTHON}`)
  })
  backend.on('exit', (code) => {
    backend = null
    if (!quitting && code !== 0) {
      dialog.showErrorBox(
        'IMS',
        `O servidor local terminou (código ${code}).\n\n${recentOutput.slice(-15).join('\n')}`,
      )
    }
  })
}

function stopBackend() {
  quitting = true
  if (backend) {
    backend.kill()
    backend = null
  }
}

function createWindow() {
  const win = new BrowserWindow({
    width: 1280,
    height: 800,
    title: 'IMS',
    autoHideMenuBar: true,
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  })

  if (app.isPackaged) {
    // Packaged builds serve the compiled UI from disk. Backend packaging is a later step.
    win.loadFile(path.join(__dirname, '..', 'dist', 'index.html'))
  } else {
    win.loadURL(DEV_URL)
  }
}

app.whenReady().then(() => {
  startBackend()
  createWindow()
  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow()
  })
})

app.on('window-all-closed', () => {
  app.quit()
})

app.on('before-quit', stopBackend)
