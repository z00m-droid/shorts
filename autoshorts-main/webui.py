#!/usr/bin/env python3
"""Локальный веб-интерфейс AutoShorts. Доступен только на localhost."""
import json, os, re, subprocess, sys, threading, time, mimetypes
from pathlib import Path
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse
from shorts import youtube_auth

ROOT = Path(__file__).resolve().parent
STATE = {"running": False, "total": 0, "done": 0, "current": "", "phase": "Ожидает запуска", "logs": [], "error": "", "outputs": [], "clips": [], "exit_code": None}
LOCK = threading.Lock()
INBOX = ROOT / 'inbox'

PAGE = r'''<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>AutoShorts Studio</title><style>
:root{color-scheme:dark;--bg:#0b0e14;--panel:#121722;--panel2:#171e2b;--line:#252e3d;--muted:#8d9aaf;--text:#edf2fb;--accent:#a8ef42;--blue:#657dff}*{box-sizing:border-box}body{margin:0;background:radial-gradient(ellipse at 85% -10%,#202c46 0,transparent 38%),var(--bg);color:var(--text);font:15px/1.5 Inter,Segoe UI,Arial,sans-serif}.wrap{max-width:1120px;margin:auto;padding:34px 24px 60px}.top{display:flex;align-items:center;justify-content:space-between;margin-bottom:34px}.brand{display:flex;gap:12px;align-items:center;font-size:20px;font-weight:750;letter-spacing:-.5px}.logo{width:38px;height:38px;border-radius:12px;background:linear-gradient(135deg,var(--accent),#6ecbff);display:grid;place-items:center;color:#111;font-weight:900}.local{font-size:12px;color:var(--muted);border:1px solid var(--line);padding:6px 10px;border-radius:30px}.hero{margin-bottom:25px}.hero h1{font-size:30px;letter-spacing:-1px;margin:0 0 5px}.hero p{color:var(--muted);margin:0}.grid{display:grid;grid-template-columns:1.2fr .8fr;gap:18px}.panel{background:linear-gradient(180deg,#151c28,#111722);border:1px solid var(--line);border-radius:18px;padding:22px;box-shadow:0 18px 50px #0002}.panel h2{font-size:16px;margin:0 0 16px}.tabs{display:flex;background:#0c111a;border:1px solid var(--line);border-radius:12px;padding:4px;gap:4px;margin-bottom:18px}.tab{flex:1;padding:10px;border:0;border-radius:9px;background:transparent;color:var(--muted);font-weight:650;cursor:pointer}.tab.active{background:#252f40;color:white}.drop{border:1px dashed #46546a;border-radius:14px;padding:25px 16px;text-align:center;background:#0e141e;transition:.2s}.drop.over{border-color:var(--accent);background:#182317}.drop strong{display:block;margin:8px 0 3px}.drop p{color:var(--muted);font-size:13px;margin:0 0 13px}.actions{display:flex;justify-content:center;gap:8px;flex-wrap:wrap}.btn{border:1px solid var(--line);background:#202a39;color:var(--text);padding:9px 13px;border-radius:9px;cursor:pointer;font-weight:600}.btn:hover{border-color:#687b9b}.btn.primary{background:var(--accent);color:#111;border-color:var(--accent);font-weight:800}.btn:disabled{opacity:.45;cursor:not-allowed}.field{margin-top:17px}.field label{display:block;color:#c8d1df;font-size:13px;margin-bottom:7px}.input{width:100%;border:1px solid var(--line);background:#0c121b;color:var(--text);padding:11px 12px;border-radius:9px;outline:none}.input:focus{border-color:#7187ff}.hint{font-size:12px;color:var(--muted);margin-top:6px}.filelist{margin-top:13px;display:grid;gap:7px}.file{display:flex;align-items:center;justify-content:space-between;background:#192231;border-radius:9px;padding:8px 10px;font-size:13px}.file span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.file small{color:var(--muted);margin-left:10px}.options{display:grid;gap:12px}.option{display:flex;gap:10px;align-items:flex-start;padding:12px;border:1px solid var(--line);border-radius:12px;background:#0f151f;cursor:pointer}.option:has(input:checked){border-color:#8292ff;background:#171f31}.option input{accent-color:var(--accent);margin-top:4px}.option b{display:block;font-size:14px}.option small{color:var(--muted);display:block;margin-top:2px}.row{display:grid;grid-template-columns:1fr 1fr;gap:12px}.start{width:100%;padding:14px;font-size:15px;margin-top:20px}.progressbox{margin-top:18px}.progressline{height:8px;background:#252e3d;border-radius:20px;overflow:hidden}.progressfill{height:100%;width:0;background:linear-gradient(90deg,var(--accent),#6fd4ff);transition:width .3s}.progressmeta{display:flex;justify-content:space-between;color:var(--muted);font-size:12px;margin:8px 0}.logs{height:180px;overflow:auto;background:#090e15;border:1px solid var(--line);border-radius:10px;padding:11px;font:12px/1.55 Consolas,monospace;color:#b6c4d8;white-space:pre-wrap}.status{font-size:13px;color:var(--muted);margin-bottom:10px}.status.good{color:var(--accent)}.foot{color:#69768b;text-align:center;font-size:12px;margin-top:22px}@media(max-width:800px){.grid{grid-template-columns:1fr}.wrap{padding:22px 14px}.hero h1{font-size:25px}.row{grid-template-columns:1fr}}
</style></head><body><main class="wrap"><header class="top"><div class="brand"><div class="logo">AS</div>AutoShorts <span style="color:#8795aa;font-weight:500">Studio</span></div><div class="local">● работает локально на этом ПК</div></header><section class="hero"><h1>Превращай длинные видео в Shorts</h1><p>Добавь видео или ссылку, выбери режим и запусти нарезку.</p></section><div class="grid"><section class="panel"><h2>01 · Источник видео</h2><div class="tabs"><button class="tab active" data-tab="files">Файлы и папки</button><button class="tab" data-tab="url">Ссылка</button></div><div class="authbox" style="margin:0 0 16px;padding:14px;border:1px solid #39445a;border-radius:13px;background:#101827"><div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap"><div style="font-weight:700">Подключение YouTube</div><span id="ytState" class="status">Проверяем браузер…</span><button class="btn" id="ytConnect" type="button">Использовать мой Google-аккаунт</button><button class="btn" id="ytCheck" type="button">Проверить подключение</button></div><div class="hint" style="margin-top:8px">Откроется YouTube в твоём обычном браузере. Если ты уже вошёл в Google, повторно вводить пароль не нужно: AutoShorts использует существующий профиль. Для чтения cookies браузер иногда потребуется закрыть перед обработкой. Для PO Token один раз запусти setup_youtube_auth.bat.</div><div id="ytMessage" class="hint"></div></div><div id="filesPane"><div class="drop" id="drop"><div style="font-size:26px">↥</div><strong>Перетащи видео сюда</strong><p>или выбери файлы / целую папку на компьютере</p><div class="actions"><label class="btn" for="filePick">Выбрать файлы</label><label class="btn" for="folderPick">Выбрать папку</label></div><input id="filePick" type="file" accept="video/*" multiple hidden><input id="folderPick" type="file" webkitdirectory multiple hidden></div><div id="fileList" class="filelist"></div><div class="hint">Можно выбрать сразу несколько файлов или целую папку. Также поддерживается перетаскивание.</div></div><div id="urlPane" style="display:none"><div class="field" style="margin-top:0"><label for="url">Ссылка на YouTube / Twitch / другой поддерживаемый источник</label><input class="input" id="url" placeholder="https://..."></div><label class="option" style="margin-top:12px"><input type="checkbox" id="live"><span><b>Это прямой эфир</b><small>Записывать Twitch / YouTube Live до завершения трансляции. Если запись с начала недоступна, начнём с текущего момента.</small></span></label><div class="hint">Для YouTube программа попробует доступные способы авторизации. Если платформа блокирует загрузку, покажет конкретную причину.</div></div><div class="field"><label for="outPath">Папка для готовых клипов</label><div style="display:flex;gap:8px"><input class="input" id="outPath" value="results" placeholder="Выбери папку для готовых клипов" readonly><button class="btn" id="browseOut" type="button">Выбрать папку…</button></div></div></section><section class="panel"><h2>02 · Настройки нарезки</h2><div class="options"><label class="option"><input type="radio" name="mode" value="game" checked><span><b>Игра</b><small>Квадратный игровой кадр 1:1, размытая подложка 9:16.</small></span></label><label class="option"><input type="radio" name="mode" value="streamer"><span><b>Игра + стример</b><small>Веб-камера сверху, игровой процесс снизу.</small></span></label></div><div class="row"><div class="field"><label for="count">Количество клипов</label><input class="input" id="count" type="number" min="1" max="30" value="5"></div><div class="field"><label for="model">Модель распознавания</label><select class="input" id="model"><option value="base">Base · быстрее</option><option value="small">Small · точнее</option><option value="tiny">Tiny · быстрее всего</option></select></div></div><div class="row"><div class="field"><label for="durationMode">Продолжительность клипа</label><select class="input" id="durationMode"><option value="auto">Автоматически · 15–60 сек</option><option value="custom">Своя продолжительность</option></select></div><div class="field" id="durationWrap" style="display:none"><label for="duration">Длина, секунд</label><input class="input" id="duration" type="number" min="10" max="180" value="30"></div></div><div class="field"><label>Отбор моментов</label><div class="options"><label class="option"><input type="radio" name="assist" value="smart" checked><span><b>Расширенный отбор</b><small>Анализ речи, громкости, пауз и доступных сигналов; точность зависит от записи.</small></span></label><label class="option"><input type="radio" name="assist" value="fast"><span><b>Быстрый отбор</b><small>Эвристики без дополнительных агентов. Быстрее, но менее избирательно.</small></span></label></div></div><div class="field"><label for="look">Улучшение картинки</label><select class="input" id="look"><option value="none">Без обработки</option><option value="cinema">Сочный киношный</option><option value="warm">Тёплый</option><option value="cold">Холодный</option></select></div><div class="row"><label class="option"><input type="checkbox" id="punch"><span><b>Динамический зум</b><small>Лёгкий акцент на громких моментах.</small></span></label><label class="option"><input type="checkbox" id="title"><span><b>Заголовок-крючок</b><small>Короткий заголовок в начале клипа.</small></span></label></div><div class="field"><label for="style">Стиль субтитров</label><select class="input" id="style"><option value="stream">Stream · жёлтый акцент</option><option value="soft">Soft · мягкий белый</option><option value="clean">Clean · минималистичный</option><option value="bold">Bold · крупный капс</option><option value="cinema">Cinema · фразами</option></select></div><button class="btn primary start" id="start">Начать обработку →</button><div class="hint">Обработка может занять время. Не закрывай это окно, пока задача выполняется.</div></section></div><section class="panel progressbox"><div style="display:flex;justify-content:space-between;gap:10px;align-items:center"><h2 style="margin:0 0 10px">03 · Прогресс обработки</h2><div id="status" class="status">Ожидает запуска</div></div><div class="progressline"><div class="progressfill" id="fill"></div></div><div class="progressmeta"><span id="progressText">0 из 0 файлов</span><span id="percent">0%</span></div><div class="logs" id="logs">Здесь появятся сообщения о скачивании, анализе и создании клипов.</div><pre id="errorDetail" class="logs" style="display:none;border-color:#7a3943;color:#ffb7bd;white-space:pre-wrap;height:auto;max-height:260px"></pre><div id="clipCards" class="filelist"></div><div id="outputs" class="hint"></div></section><div class="foot">AutoShorts Studio · локальный интерфейс · видео обрабатываются на твоём компьютере</div></main><script>
const $=id=>document.getElementById(id);let files=[];let tab='files';$('durationMode').onchange=()=>{$('durationWrap').style.display=$('durationMode').value==='custom'?'block':'none'};const previewUrls=new Map();const esc=s=>String(s??'').replace(/[&<>\"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',"'":'&#39;'}[c]));function addFiles(list){for(const f of list){if(f.type.startsWith('video/')||/\.(mp4|mkv|mov|avi|webm|m4v|flv|ts|wmv|mpg|mpeg)$/i.test(f.name)){const key=(f.webkitRelativePath||f.name)+'|'+f.size+'|'+f.lastModified;if(!files.some(x=>(x.webkitRelativePath||x.name)+'|'+x.size+'|'+x.lastModified===key))files.push(f)}}renderFiles()}function renderFiles(){for(const u of previewUrls.values())URL.revokeObjectURL(u);previewUrls.clear();$('fileList').innerHTML=files.map((f,i)=>{const u=URL.createObjectURL(f);previewUrls.set(i,u);return `<div class="file"><video muted playsinline preload="metadata" src="${u}" style="width:58px;height:42px;object-fit:cover;border-radius:6px;background:#080b10"></video><span style="flex:1;margin-left:9px">${esc(f.webkitRelativePath||f.name)}</span><small>${(f.size/1024/1024).toFixed(1)} MB <a href="#" data-i="${i}" style="color:#ff8f8f;margin-left:8px">×</a></small></div>`}).join('');$('fileList').querySelectorAll('a').forEach(a=>a.onclick=e=>{e.preventDefault();files.splice(+a.dataset.i,1);renderFiles()})}
$('filePick').onchange=e=>addFiles(e.target.files);$('folderPick').onchange=e=>addFiles(e.target.files);const drop=$('drop');['dragenter','dragover'].forEach(x=>drop.addEventListener(x,e=>{e.preventDefault();drop.classList.add('over')}));['dragleave','drop'].forEach(x=>drop.addEventListener(x,e=>{e.preventDefault();drop.classList.remove('over')}));drop.ondrop=e=>addFiles(e.dataTransfer.files);
$('browseOut').onclick=async()=>{try{let r=await fetch('/api/browse-output');let j=await r.json();if(j.path)$('outPath').value=j.path}catch(e){alert('Не удалось открыть выбор папки. Укажи путь вручную.')}};
document.querySelectorAll('.tab').forEach(b=>b.onclick=()=>{tab=b.dataset.tab;document.querySelectorAll('.tab').forEach(x=>x.classList.toggle('active',x===b));$('filesPane').style.display=tab==='files'?'block':'none';$('urlPane').style.display=tab==='url'?'block':'none'});
async function refreshYT(){try{let r=await fetch('/api/youtube/status');let j=await r.json();$('ytState').textContent=j.connected?'Профиль найден':'Не подключён';$('ytState').className='status '+(j.connected?'good':'');$('ytMessage').textContent=j.message||''}catch(e){$('ytState').textContent='Недоступно'}}
$('ytConnect').onclick=async()=>{ $('ytConnect').disabled=true;try{let r=await fetch('/api/youtube/connect',{method:'POST'});let j=await r.json();$('ytMessage').textContent=j.message||j.error||'';await refreshYT()}catch(e){$('ytMessage').textContent='Не удалось открыть Edge'}finally{$('ytConnect').disabled=false}};
$('ytCheck').onclick=async()=>{ $('ytCheck').disabled=true;try{let r=await fetch('/api/youtube/check',{method:'POST'});let j=await r.json();$('ytMessage').textContent=j.message||j.error||'';await refreshYT()}catch(e){$('ytMessage').textContent='Ошибка проверки'}finally{$('ytCheck').disabled=false}};refreshYT();
async function poll(){try{let s=await(await fetch('/api/status')).json();$('status').textContent=s.running?(s.phase||'Обработка…'):s.error?'Завершено с ошибкой':s.done&&s.done===s.total?'Готово':(s.phase||'Ожидает запуска');$('status').className='status '+(!s.running&&s.done===s.total&&s.total?'good':'');let pct=s.total?Math.round(s.done/s.total*100):0;$('fill').style.width=pct+'%';$('percent').textContent=pct+'%';$('progressText').textContent=`${s.done} из ${s.total} файлов`;$('logs').textContent=(s.logs||[]).join('\n');$('logs').scrollTop=$('logs').scrollHeight;$('errorDetail').textContent=s.error||'';$('errorDetail').style.display=s.error?'block':'none';$('outputs').textContent=s.outputs?.length?'Готовые папки: '+s.outputs.join(' · '):'';$('clipCards').innerHTML=(s.clips||[]).map(c=>`<div class="file"><img src="/api/media?f=${encodeURIComponent(c.cover||'')}" style="width:58px;height:94px;object-fit:cover;border-radius:7px;background:#080b10"><span style="flex:1;margin-left:9px"><b>${esc(c.title||'Клип '+c.index)}</b><small style="display:block">${c.index}/${c.total} · ${Math.round(c.progress||0)}% · ${c.status||'В очереди'} · ${Math.round((c.end||0)-(c.start||0))} сек.</small></span><a href="/api/media?f=${encodeURIComponent(c.file||'')}" target="_blank" style="color:#a8ef42">Видео</a></div>`).join('');$('start').disabled=s.running}catch(e){}setTimeout(poll,1200)}poll();
$('start').onclick=async()=>{let mode=document.querySelector('[name=mode]:checked').value;let data={tab,mode,count:+$('count').value||5,model:$('model').value,style:$('style').value,outPath:$('outPath').value||'results',url:$('url').value,live:$('live').checked,durationMode:$('durationMode').value,duration:+$('duration').value||30,assist:document.querySelector('[name=assist]:checked').value,look:$('look').value,punch:$('punch').checked,title:$('title').checked};if(tab==='url'&&!data.url.trim())return alert('Вставь ссылку на видео.');if(tab==='files'&&!files.length)return alert('Выбери видеофайлы или папку с видео.');let fd=new FormData();fd.append('data',JSON.stringify(data));if(tab==='files')files.forEach(f=>fd.append('files',f,f.name));$('start').disabled=true;$('status').textContent='Подготовка…';try{let r=await fetch('/api/start',{method:'POST',body:fd});let j=await r.json();if(!r.ok)alert(j.error||'Не удалось запустить')}catch(e){alert('Не удалось связаться с локальным сервером. Перезапусти start_webui.bat.')}finally{setTimeout(async()=>{try{let s=await(await fetch('/api/status')).json();$('start').disabled=!!s.running}catch(e){$('start').disabled=false}},250)}};
</script></body></html>'''


def log(msg):
    with LOCK:
        STATE['logs'].append(str(msg).rstrip())
        STATE['logs'] = STATE['logs'][-160:]

def run_jobs(data, uploaded):
    """Run one job at a time and never report success unless output files exist."""
    try:
        mode = data.get('mode', 'game')
        if mode not in ('game', 'streamer'):
            raise ValueError(f'Неизвестный режим: {mode}')
        layout = 'game' if mode == 'game' else 'split'
        count = max(1, min(30, int(data.get('count', 5))))
        model = data.get('model', 'base')
        if model not in ('tiny', 'base', 'small'):
            raise ValueError(f'Неизвестная модель Whisper: {model}')
        out_root = Path(data.get('outPath') or 'results').expanduser()
        if not out_root.is_absolute(): out_root = ROOT / out_root
        out_root.mkdir(parents=True, exist_ok=True)
        sources = list(uploaded)
        url = str(data.get('url', '')).strip()
        if data.get('tab') == 'url' and url:
            sources = [url]
        if not sources:
            raise ValueError('Не найдены видео для обработки.')
        with LOCK:
            STATE.update(total=len(sources), done=0, current='', outputs=[], clips=[], error='', phase='Подготовка', exit_code=None)
        for idx, src in enumerate(sources, 1):
            is_url = str(src).lower().startswith(('http://', 'https://'))
            label = str(src) if is_url else Path(src).name
            with LOCK:
                STATE['current'] = label
                STATE['phase'] = f'Запуск {idx}/{len(sources)}'
            log(f'[{idx}/{len(sources)}] Начинаю: {label}')
            name = re.sub(r'[^\w.-]+', '_', Path(label).stem)[:60] or f'video_{idx}'
            dest = out_root / name
            dest.mkdir(parents=True, exist_ok=True)
            cmd = [sys.executable, '-u', str(ROOT/'autoshorts.py'), str(src), '-n', str(count), '--layout', layout,
                   '--model', model, '--style', data.get('style','stream'), '--look', data.get('look','none'), '-o', str(dest)]
            if data.get('assist') == 'fast': cmd += ['--quick']
            if data.get('durationMode') == 'custom':
                seconds = max(10, min(180, int(data.get('duration', 30))))
                cmd += ['--min', str(seconds), '--max', str(seconds)]
            if data.get('punch'): cmd += ['--punch']
            if data.get('title'): cmd += ['--title']
            if data.get('live') and is_url: cmd += ['--live']
            if is_url: cmd += ['--cookies-from-browser', 'auto']
            log('Команда: ' + subprocess.list2cmdline(cmd))
            env = os.environ.copy()
            env['PYTHONUNBUFFERED'] = '1'
            env['PYTHONUTF8'] = '1'
            env['AUTOSHORTS_YOUTUBE_PROFILE'] = youtube_auth.profile_name()
            env['AUTOSHORTS_YOUTUBE_BROWSER'] = youtube_auth.detect_browser()
            with LOCK: STATE['phase'] = 'Загрузка источника' if is_url else 'Проверка видео'
            proc = subprocess.Popen(cmd, cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    text=True, encoding='utf-8', errors='replace', bufsize=1, env=env)
            tail = []
            for line in proc.stdout:
                line = line.rstrip('\r\n')
                tail.append(line); tail = tail[-80:]
                if line.startswith('@@CLIP_START@@'):
                    try:
                        clip = json.loads(line[len('@@CLIP_START@@'):])
                        clip.update(progress=0, status='Рендеринг')
                        with LOCK: STATE['clips'] = [x for x in STATE['clips'] if x.get('file') != clip.get('file')] + [clip]
                        STATE['phase'] = f'Рендер клипа {clip.get("index", "")}/{clip.get("total", "")}'
                    except Exception as e: log('Не удалось разобрать событие начала клипа: ' + str(e))
                elif line.startswith('@@CLIP@@'):
                    try:
                        clip = json.loads(line[len('@@CLIP@@'):])
                        clip.update(progress=100, status='Готово')
                        with LOCK: STATE['clips'] = [x for x in STATE['clips'] if x.get('file') != clip.get('file')] + [clip]
                        STATE['phase'] = f'Готово клипов: {len(STATE["clips"])}'
                    except Exception as e: log('Не удалось разобрать событие готового клипа: ' + str(e))
                else:
                    if line.startswith('▶') or 'распознавание' in line.lower() or 'движение' in line.lower():
                        with LOCK: STATE['phase'] = line[:140]
                    log(line)
            rc = proc.wait()
            made = sorted(str(x) for x in dest.glob('short_*.mp4') if x.is_file() and x.stat().st_size > 10_000)
            if rc != 0 or not made:
                detail = '\n'.join(tail[-18:]) or 'Процесс завершился без диагностического вывода.'
                reason = f'{label}: код завершения {rc}; готовых клипов: {len(made)}\n{detail}'
                log('ОШИБКА: ' + reason)
                with LOCK:
                    STATE['error'] = (STATE['error'] + '\n\n' if STATE['error'] else '') + reason
                    STATE['exit_code'] = rc
            else:
                log(f'ГОТОВО: {dest} — создано файлов: {len(made)}')
                with LOCK: STATE['outputs'].append(str(dest))
            with LOCK: STATE['done'] = idx
        with LOCK:
            STATE['phase'] = 'Завершено с ошибками' if STATE['error'] else 'Все задачи завершены'
        log('Пакетная обработка завершена.')
    except Exception as e:
        import traceback
        detail = traceback.format_exc(limit=8)
        with LOCK:
            STATE['error'] = f'{type(e).__name__}: {e}\n{detail}'
            STATE['phase'] = 'Внутренняя ошибка веб-интерфейса'
        log('ОШИБКА: ' + str(e))
    finally:
        with LOCK: STATE['running'] = False

class Handler(BaseHTTPRequestHandler):
    def _json(self, obj, code=200):
        raw=json.dumps(obj,ensure_ascii=False).encode(); self.send_response(code); self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Content-Length',str(len(raw))); self.end_headers(); self.wfile.write(raw)
    def do_GET(self):
        path=urlparse(self.path).path
        if path=='/':
            raw=PAGE.encode(); self.send_response(200); self.send_header('Content-Type','text/html; charset=utf-8'); self.send_header('Content-Length',str(len(raw))); self.end_headers(); self.wfile.write(raw)
        elif path=='/api/youtube/status':
            ready = youtube_auth.profile_ready()
            self._json({'connected': ready, 'message': youtube_auth.status_message()})
        elif path=='/api/status':
            with LOCK: self._json(dict(STATE))
        elif path=='/api/media':
            from urllib.parse import parse_qs
            target = parse_qs(urlparse(self.path).query).get('f', [''])[0]
            if not target or not os.path.isfile(target): self.send_error(404); return
            resolved = Path(target).resolve()
            try: resolved.relative_to(ROOT.resolve())
            except ValueError: self.send_error(403); return
            target = str(resolved)
            mime = mimetypes.guess_type(target)[0] or 'application/octet-stream'
            size = os.path.getsize(target)
            self.send_response(200); self.send_header('Content-Type', mime); self.send_header('Content-Length', str(size)); self.send_header('Cache-Control','no-store'); self.end_headers()
            with open(target, 'rb') as f:
                while True:
                    chunk=f.read(1024*1024)
                    if not chunk: break
                    self.wfile.write(chunk)
        elif path=='/api/browse-output':
            try:
                import tkinter as tk
                from tkinter import filedialog
                root=tk.Tk(); root.withdraw(); root.attributes('-topmost',True)
                chosen=filedialog.askdirectory(title='Папка для готовых клипов'); root.destroy()
                self._json({'path':chosen})
            except Exception as e: self._json({'error':str(e)},500)
        else: self.send_error(404)
    def do_POST(self):
        if self.path == '/api/youtube/connect':
            try:
                info = youtube_auth.launch_login()
                self._json({'ok': True, 'message': 'Открыл YouTube в основном браузере (' + info['browser'] + ', профиль ' + info['profile'] + '). Если аккаунт уже авторизован, ничего вводить заново не нужно. Для чтения cookies закрой браузер перед проверкой.'})
            except Exception as e: self._json({'error': str(e)}, 500)
            return
        if self.path == '/api/youtube/check':
            if not youtube_auth.profile_ready():
                self._json({'ok': False, 'message': 'Профиль ещё не создан. Сначала нажми «Войти через Google».'}, 400); return
            try:
                import yt_dlp
                test_url = 'https://www.youtube.com/watch?v=BaW_jenozKc'
                opts = {'quiet': True, 'no_warnings': True, 'skip_download': True, 'cookiesfrombrowser': youtube_auth.yt_dlp_cookie_tuple()}
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(test_url, download=False)
                self._json({'ok': True, 'message': 'Проверка YouTube прошла: yt-dlp прочитал профиль и получил видео «' + str(info.get('title') or 'тест')[:90] + '». Можно пробовать свои ссылки.'})
            except Exception as e: self._json({'ok': False, 'message': 'Не удалось прочитать cookies текущего профиля. Закрой браузер полностью и повтори проверку. Детали: ' + str(e)[:500]}, 400)
            return
        if self.path!='/api/start': self.send_error(404); return
        with LOCK:
            if STATE['running']:
                self._json({'error':'Обработка уже выполняется.'},409); return
        length=int(self.headers.get('Content-Length','0'))
        if length>8*1024*1024*1024: self._json({'error':'Слишком большой запрос.'},413); return
        from email.parser import BytesParser
        from email.policy import default
        raw=self.rfile.read(length)
        msg=BytesParser(policy=default).parsebytes((f'Content-Type: {self.headers.get("Content-Type","")}\r\nMIME-Version: 1.0\r\n\r\n').encode()+raw)
        fields={} ; uploaded=[]
        for item in msg.iter_parts():
            key=item.get_param('name',header='content-disposition')
            filename=item.get_filename()
            payload=item.get_payload(decode=True) or b''
            if key=='data': fields['data']=payload.decode('utf-8','replace')
            elif key=='files' and filename:
                safe=Path(filename).name
                dest=INBOX/safe; dest.parent.mkdir(parents=True,exist_ok=True)
                stem,suffix=dest.stem,dest.suffix; n=1
                while dest.exists(): dest=INBOX/f'{stem}_{n}{suffix}'; n+=1
                with open(dest,'wb') as f: f.write(payload)
                uploaded.append(str(dest))
        try: data=json.loads(fields.get('data','{}'))
        except Exception: self._json({'error':'Некорректные настройки.'},400); return
        with LOCK:
            STATE.update(running=True,total=0,done=0,current='',phase='Приём задачи',logs=[],error='',outputs=[],clips=[],exit_code=None)
        threading.Thread(target=run_jobs,args=(data,uploaded),daemon=True).start()
        self._json({'ok':True})
    def log_message(self,*args): pass

if __name__=='__main__':
    server=ThreadingHTTPServer(('127.0.0.1',8765),Handler)
    print('AutoShorts Studio: http://127.0.0.1:8765')
    try:
        import webbrowser; threading.Timer(1.0,lambda:webbrowser.open('http://127.0.0.1:8765')).start()
    except Exception: pass
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()
