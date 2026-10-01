// Drives the running Electron window over the DevTools protocol (dev/test helper).
const http = require('http')

function getJson(url) {
  return new Promise((res, rej) => http.get(url, (r) => { let d = ''; r.on('data', (c) => d += c); r.on('end', () => res(JSON.parse(d))) }).on('error', rej))
}

async function main() {
  const targets = await getJson('http://127.0.0.1:9333/json')
  const page = targets.find((t) => t.type === 'page')
  const ws = new WebSocket(page.webSocketDebuggerUrl)
  await new Promise((r) => (ws.onopen = r))
  let id = 0
  const pending = new Map()
  ws.onmessage = (m) => { const d = JSON.parse(m.data); if (d.id && pending.has(d.id)) { pending.get(d.id)(d); pending.delete(d.id) } }
  const evalJs = (expr) => new Promise((resolve) => {
    const i = ++id; pending.set(i, resolve)
    ws.send(JSON.stringify({ id: i, method: 'Runtime.evaluate', params: { expression: expr, awaitPromise: true, returnByValue: true } }))
  }).then((d) => d.result.result.value ?? d.result.exceptionDetails)
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
  const waitText = async (t, ms = 240000) => {
    const s = Date.now()
    while (Date.now() - s < ms) { if (await evalJs(`document.body.innerText.toLowerCase().includes(${JSON.stringify(t)}.toLowerCase())`)) return true; await sleep(700) }
    return false
  }

  console.log('title:', await evalJs('document.title'))
  console.log('bridge:', await evalJs('typeof window.localrepo + "/" + typeof (window.localrepo||{}).pickFolder'))
  console.log('ollama badge:', await evalJs('document.querySelector(".status").innerText.replace(/\\n/g," ")'))

  // type a path (with spaces test uses separate repo) and click Load
  const repo = process.argv[2] || 'D:/Rakshak'
  await evalJs(`(() => { const i = document.querySelector('input.path'); const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set; set.call(i, ${JSON.stringify(repo)}); i.dispatchEvent(new Event('input',{bubbles:true})) })()`)
  await sleep(300)
  await evalJs(`[...document.querySelectorAll('button')].find(b=>b.innerText.trim().toLowerCase()==='load').click()`)
  console.log('loaded:', await waitText('FILES INDEXED', 60000), await evalJs('document.querySelector(".repo-name")?.innerText'))

  // ask
  await evalJs(`(() => { const i = document.querySelector('.inputbar input'); const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set; set.call(i, 'Where is FusedLocationProviderClient used?'); i.dispatchEvent(new Event('input',{bubbles:true})) })()`)
  await sleep(300)
  await evalJs(`[...document.querySelectorAll('button')].find(b=>b.innerText.toLowerCase().includes('ask ai')).click()`)
  console.log('answer:', await waitText('RELEVANT SOURCES'))
  console.log('label:', await waitText('LOCALREPO ANALYSIS', 1000))
  console.log('sources:', JSON.stringify(await evalJs('[...document.querySelectorAll(".src")].map(e=>e.innerText)')))

  // click first source -> viewer
  await evalJs('document.querySelector(".src").click()')
  await sleep(1500)
  console.log('viewer:', await evalJs('document.querySelector(".vhead span")?.innerText'), '| lines:', await evalJs('document.querySelectorAll(".ln").length'), '| highlighted:', await evalJs('document.querySelectorAll(".ln.hl").length'))

  // explain
  await evalJs(`[...document.querySelectorAll('button')].find(b=>b.innerText.trim().toLowerCase()==='explain file').click()`)
  console.log('explain:', await waitText('FILE ANALYSIS'))
  console.log('explain snippet:', (await evalJs('document.querySelector(".explain")?.innerText')).slice(0, 160).replace(/\n/g, ' '))
  ws.close()
}
main().catch((e) => { console.error(e); process.exit(1) })
