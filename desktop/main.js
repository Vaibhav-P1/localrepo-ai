const { app, BrowserWindow, dialog, ipcMain, shell } = require('electron')
const { spawn } = require('child_process')
const http = require('http')
const net = require('net')
const path = require('path')
const fs = require('fs')

const DEV = process.argv.includes('--dev')
let backend = null
let devVite = null
let win = null

function freePort() {
  return new Promise((resolve, reject) => {
    const srv = net.createServer()
    srv.listen(0, '127.0.0.1', () => {
      const { port } = srv.address()
      srv.close(() => resolve(port))
    })
    srv.on('error', reject)
  })
}

function waitFor(url, timeoutMs = 90000) {
  const start = Date.now()
  return new Promise((resolve, reject) => {
    const tick = () => {
      http.get(url, (res) => { res.resume(); resolve() }).on('error', () => {
        if (Date.now() - start > timeoutMs) reject(new Error('Timed out waiting for ' + url))
        else setTimeout(tick, 400)
      })
    }
    tick()
  })
}

const isUp = (url) => new Promise((r) => http.get(url, (res) => { res.resume(); r(true) }).on('error', () => r(false)))

async function startServices() {
  if (DEV) {
    // Dev: Vite on 5173 (proxies /api) + uvicorn on 8000, same as the browser workflow.
    const root = path.join(__dirname, '..')
    if (!(await isUp('http://127.0.0.1:8000/api/status'))) {
      backend = spawn('python', ['-m', 'uvicorn', 'main:app', '--host', '127.0.0.1', '--port', '8000'],
        { cwd: path.join(root, 'backend'), windowsHide: true })
    }
    if (!(await isUp('http://localhost:5173'))) {
      devVite = spawn('npm', ['run', 'dev'], { cwd: path.join(root, 'frontend'), shell: true, windowsHide: true })
    }
    await waitFor('http://127.0.0.1:8000/api/status')
    await waitFor('http://localhost:5173')
    return 'http://localhost:5173'
  }

  // Packaged (or electron:start): the bundled backend serves the built UI on a free localhost port.
  const port = await freePort()
  const base = app.isPackaged ? process.resourcesPath : path.join(__dirname, '..')
  const uiDir = app.isPackaged ? path.join(base, 'ui') : path.join(base, 'frontend', 'dist')
  const backendDir = app.isPackaged ? path.join(base, 'backend') : path.join(base, 'backend', 'dist', 'localrepo-backend')
  const exe = path.join(backendDir, 'localrepo-backend.exe')
  if (fs.existsSync(exe)) {
    backend = spawn(exe, ['--port', String(port), '--static', uiDir], { windowsHide: true })
  } else {
    backend = spawn('python', ['server.py', '--port', String(port), '--static', uiDir],
      { cwd: path.join(__dirname, '..', 'backend'), windowsHide: true })
  }
  backend.stderr.on('data', (d) => console.error('[backend]', d.toString()))
  backend.on('exit', (code) => { backend = null; if (code) console.error('backend exited', code) })
  await waitFor('http://127.0.0.1:' + port + '/api/status')
  return 'http://127.0.0.1:' + port
}

function stopServices() {
  for (const p of [backend, devVite]) {
    if (p && p.pid) spawn('taskkill', ['/pid', String(p.pid), '/T', '/F'], { windowsHide: true })
  }
  backend = devVite = null
}

async function createWindow() {
  win = new BrowserWindow({
    width: 1400, height: 880, minWidth: 1000, minHeight: 650,
    title: 'LocalRepo AI', backgroundColor: '#f4ecd8', autoHideMenuBar: true,
    webPreferences: { preload: path.join(__dirname, 'preload.js'), contextIsolation: true, nodeIntegration: false, sandbox: true },
  })
  win.loadURL('data:text/html;charset=utf-8,' + encodeURIComponent(
    '<body style="font-family:sans-serif;background:#f4ecd8;padding:40px"><h2>Starting LocalRepo AI...</h2></body>'))
  try {
    const url = await startServices()
    // Never navigate away from our own local origin; open other links in the OS browser.
    win.webContents.setWindowOpenHandler(({ url: u }) => { shell.openExternal(u); return { action: 'deny' } })
    win.webContents.on('will-navigate', (e, u) => { if (!u.startsWith(url)) { e.preventDefault(); shell.openExternal(u) } })
    await win.loadURL(url)
  } catch (err) {
    dialog.showErrorBox('LocalRepo AI could not start', String(err))
    app.quit()
  }
}

ipcMain.handle('pick-folder', async () => {
  const r = await dialog.showOpenDialog(win, { title: 'Select repository folder', properties: ['openDirectory'] })
  return r.canceled || !r.filePaths.length ? null : r.filePaths[0]
})
ipcMain.handle('open-external', (_e, url) => {
  if (typeof url === 'string' && /^https:\/\/(www\.)?ollama\.com\//.test(url)) return shell.openExternal(url)
})

if (!app.requestSingleInstanceLock()) app.quit()
else {
  app.on('second-instance', () => { if (win) { if (win.isMinimized()) win.restore(); win.focus() } })
  app.whenReady().then(createWindow)
  app.on('window-all-closed', () => app.quit())
  app.on('before-quit', stopServices)
  app.on('will-quit', stopServices)
}
