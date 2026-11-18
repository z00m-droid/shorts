"""Раскладка кадра 9:16: поиск вебки стримера и сборка фильтра ffmpeg.

split  — вебка сверху, игра (или фон) снизу, субтитры на стыке (как в нарезках со стримов)
face   — весь кадр 9:16 вокруг лица (IRL, подкасты)
fit    — горизонтальное видео целиком по центру на размытом фоне
"""
import os
import numpy as np

def _cascade(name):
    """Каскад OpenCV, прочитанный из памяти: на Windows OpenCV не открывает путь с кириллицей (C:\\Users\\Владимир\\...)."""
    import cv2
    path = os.path.join(cv2.data.haarcascades, name)
    with open(path, encoding='utf-8') as f: xml = f.read()
    c = cv2.CascadeClassifier()
    fs = cv2.FileStorage(xml, cv2.FILE_STORAGE_READ | cv2.FILE_STORAGE_MEMORY)
    if not c.read(fs.getFirstTopLevelNode()) or c.empty(): raise RuntimeError(f'не загрузился каскад {name}')
    return c


class FaceFinder:
    """Детектор лиц: нейросетевой YuNet (models/, видит повёрнутые и мелкие лица), иначе haar-каскады OpenCV."""
    MODEL = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'models', 'face_detection_yunet_2023mar.onnx')

    def __init__(self):
        import cv2
        self.cv2 = cv2; self.yn = None
        if os.path.isfile(self.MODEL) and hasattr(cv2, 'FaceDetectorYN'):
            try:
                with open(self.MODEL, 'rb') as f: buf = np.frombuffer(f.read(), np.uint8)   # из памяти: кириллица в пути не мешает
                self.yn = cv2.FaceDetectorYN.create('onnx', buf, np.array([], np.uint8), (320, 320), 0.75, 0.3, 50)
            except Exception:
                self.yn = None
        if self.yn is None:
            self.fr = _cascade('haarcascade_frontalface_default.xml'); self.pr = _cascade('haarcascade_profileface.xml')

    def find(self, bgr, min_px):
        """Лица на кадре BGR: [(x, y, w, h)]."""
        cv2 = self.cv2
        if self.yn is not None:
            h, w = bgr.shape[:2]; self.yn.setInputSize((w, h))
            _, faces = self.yn.detect(bgr)
            return [tuple(int(v) for v in f[:4]) for f in (faces if faces is not None else []) if f[3] >= min_px]
        g = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY); ms = (min_px, min_px)
        fs = list(self.fr.detectMultiScale(g, 1.1, 5, minSize=ms)) + list(self.pr.detectMultiScale(g, 1.1, 5, minSize=ms))
        gw = g.shape[1]
        fs += [(gw - x - w, y, w, h) for x, y, w, h in self.pr.detectMultiScale(cv2.flip(g, 1), 1.1, 5, minSize=ms)]
        return [tuple(int(v) for v in f) for f in fs]


_finder = None


def finder():
    global _finder
    if _finder is None: _finder = FaceFinder()
    return _finder


def _open(video):
    import cv2
    cap = cv2.VideoCapture(video)
    if not cap.isOpened(): raise RuntimeError('OpenCV не открыл видео')
    return cap


W, H = 1080, 1920
TOP_H = 690                    # высота верхней части в split (36 %, как в популярных нарезках)
BOT_H = H - TOP_H



_bounds_cache = {}
def content_bounds(video, vw, vh):
    """Консервативно ищет постоянные чёрные поля по краям видео."""
    key = (os.path.abspath(video), int(vw), int(vh))
    if key in _bounds_cache: return _bounds_cache[key]
    full = (0, 0, vw, vh)
    try:
        import cv2
        cap = _open(video); rows=[]; cols=[]
        for t in np.linspace(0, min(25, max(0.5, cap.get(cv2.CAP_PROP_FRAME_COUNT) / max(1, cap.get(cv2.CAP_PROP_FPS)) - 0.1)), 7):
            cap.set(cv2.CAP_PROP_POS_MSEC, float(t)*1000); ok, fr=cap.read()
            if not ok: continue
            g=cv2.cvtColor(cv2.resize(fr,(min(480,vw), max(64,int(vh*min(480,vw)/vw)))),cv2.COLOR_BGR2GRAY)
            rows.append((g.mean(axis=1), g.std(axis=1))); cols.append((g.mean(axis=0),g.std(axis=0)))
        cap.release()
        if len(rows)<3: return full
        rm=np.mean([x[0] for x in rows],axis=0); rs=np.mean([x[1] for x in rows],axis=0)
        cm=np.mean([x[0] for x in cols],axis=0); cs=np.mean([x[1] for x in cols],axis=0)
        def edges(mean,std,limit):
            ok=(mean<13)&(std<9); a=0; b=len(ok)-1
            while a < len(ok)*0.30 and ok[a]: a+=1
            while b > len(ok)*0.70 and ok[b]: b-=1
            return a,b+1
        y0,y1=edges(rm,rs,0); x0,x1=edges(cm,cs,0)
        sy=vh/len(rm); sx=vw/len(cm)
        x0,x1=int(x0*sx),int(x1*sx); y0,y1=int(y0*sy),int(y1*sy)
        if (x0>vw*.025 or y0>vh*.025 or x1<vw*.975 or y1<vh*.975) and x1-x0>vw*.55 and y1-y0>vh*.45:
            full=(x0,y0,x1-x0,y1-y0)
    except Exception:
        full=(0,0,vw,vh)
    _bounds_cache[key]=full
    return full

def motion_track(video, vw, vh, s, d, side, sample_fps=2.0, bounds=None):
    """Стабильное групповое кадрирование по активной области.

    Использует не один самый активный кластер, а объединённый центр нескольких
    крупных кластеров. Есть dead-zone около центра, защита от вспышек/склеек,
    медианное сглаживание и ограничение скорости виртуальной камеры.
    Это всё ещё CV-эвристика, не распознавание игровых персонажей.
    """
    try:
        import cv2
        cap = _open(video)
    except Exception as e:
        print(f'  (трекер игрового действия недоступен: {e}); использую центр')
        return None
    scale = min(1.0, 640.0 / max(vw, vh))
    sw, sh = max(64, int(vw * scale)), max(64, int(vh * scale))
    xs, times = [], []
    prev = None
    step = 1.0 / max(0.5, float(sample_fps))
    sample_times = np.arange(0.0, max(0.01, d), step)
    if not len(sample_times): sample_times = np.array([0.0])
    for rel_t in sample_times:
        cap.set(cv2.CAP_PROP_POS_MSEC, (s + float(rel_t)) * 1000.0)
        ok, frame = cap.read()
        if not ok: continue
        small = cv2.resize(frame, (sw, sh), interpolation=cv2.INTER_AREA)
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (7, 7), 0)
        if prev is None:
            prev = gray; continue
        diff = cv2.absdiff(gray, prev); prev = gray
        mx, my = max(2, int(sw * 0.025)), max(2, int(sh * 0.04))
        roi = diff[my:sh-my, mx:sw-mx]
        if roi.size == 0: continue
        threshold = max(16, int(np.percentile(roi, 82)))
        mask = (roi >= threshold).astype(np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        count, area = int(mask.sum()), mask.size
        # Вспышки, меню и смена сцены не должны менять цель.
        if count < max(8, int(area * 0.002)) or count > area * 0.48:
            target = vw / 2
        else:
            n, labels, stats, centroids = cv2.connectedComponentsWithStats(mask, 8)
            comps = []
            min_area = max(6, int(area * 0.0012))
            for j in range(1, n):
                a = int(stats[j, cv2.CC_STAT_AREA])
                if a >= min_area:
                    comps.append((a, float(centroids[j][0] + mx), float(centroids[j][1] + my)))
            if not comps:
                target = vw / 2
            else:
                comps.sort(key=lambda q: q[0], reverse=True)
                chosen = comps[:8]
                # Берём объединённую активную область: это удерживает двух игроков вместе.
                weights = np.asarray([q[0] for q in chosen], dtype=np.float32)
                centers = np.asarray([q[1] for q in chosen], dtype=np.float32)
                group_cx = float(np.average(centers, weights=weights)) / scale
                # Если активность уже внутри центральной зоны квадрата, фиксируем кадр.
                current_center = (vw - side) / 2 + side / 2
                dead_zone = side * 0.16
                if abs(group_cx - current_center) < dead_zone:
                    target = current_center
                else:
                    target = group_cx
        times.append(float(rel_t))
        xs.append(float(np.clip(target - side / 2, 0, vw - side)))
    cap.release()
    if not xs: return None
    arr = np.asarray(xs, dtype=np.float32)
    xmin, xmax = (int(bounds[0]), int(bounds[0] + bounds[2] - side)) if bounds else (0, vw-side)
    arr = np.clip(arr, xmin, max(xmin, xmax))
    # Медианное окно убирает одиночные всплески и короткие ложные цели.
    if len(arr) >= 3:
        arr = np.array([np.median(arr[max(0, i-2):min(len(arr), i+3)]) for i in range(len(arr))], dtype=np.float32)
    smooth = [float(np.clip((vw - side) / 2, xmin, max(xmin, xmax)))]
    max_step = max(12.0, side * 0.055)
    for target in arr[1:]:
        delta = float(target) - smooth[-1]
        if abs(delta) < side * 0.035:
            delta = 0.0
        delta = float(np.clip(delta, -max_step, max_step))
        smooth.append(float(np.clip(smooth[-1] + delta * 0.48, xmin, max(xmin, xmax))))
    keep = np.linspace(0, len(times) - 1, min(60, len(times))).round().astype(int)
    points = [(round(times[i], 3), round(smooth[i], 1)) for i in keep]
    return [(0.0, round((vw - side) / 2, 1))] + points


def _track_expr(track, default_x):
    """Piecewise-linear crop-x expression evaluated by FFmpeg on every frame."""
    if not track:
        return str(int(default_x))
    expr = f'{track[-1][1]:.1f}'
    for i in range(len(track) - 2, -1, -1):
        t0, x0 = track[i]
        t1, x1 = track[i + 1]
        span = max(0.001, t1 - t0)
        linear = f'({x0:.1f}+({x1-x0:.1f})*(t-{t0:.3f})/{span:.3f})'
        expr = f'if(lt(t,{t1:.3f}),{linear},{expr})'
    return expr


def scan_faces(video, vw, vh, t0, t1, n=40):
    """Лица в n кадрах отрезка: список (x, y, w, h) в пикселях исходника."""
    try:
        import cv2
        det = finder(); cap = _open(video)
    except Exception as e:                                         # нет OpenCV / не открылось — работаем без лиц
        print(f'  (поиск лиц недоступен: {e})'); return []
    out = []; k = 2
    for t in np.linspace(t0, t1, n):
        cap.set(cv2.CAP_PROP_POS_MSEC, float(t) * 1000); ok, fr = cap.read()
        if not ok: continue
        fs = det.find(cv2.resize(fr, (vw // k, vh // k)), max(12, vh // 80))
        for x, y, w, h in fs:
            out.append((x * k, y * k, w * k, h * k))
    cap.release()
    return out


def refine_cam(video, vw, vh, t0, t1, box, face):
    """Уточняет рамку вебки по её краям: граница оверлея — неподвижная резкая линия, а картинка внутри и снаружи меняется."""
    try:
        import cv2
    except ImportError:
        return box
    fx, fy, fw, fh = face; gx = gy = None; k = 0
    try:
        cap = _open(video)
    except Exception:
        return box
    for t in np.linspace(t0, t1, 48):
        cap.set(cv2.CAP_PROP_POS_MSEC, float(t) * 1000); ok, fr = cap.read()
        if not ok: continue
        g = cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY).astype(np.float32)
        ex, ey = np.abs(np.diff(g, axis=1)), np.abs(np.diff(g, axis=0))
        gx = ex if gx is None else gx + ex; gy = ey if gy is None else gy + ey; k += 1
    cap.release()
    if not k: return box
    gx /= k; gy /= k
    r0, r1 = int(max(0, fy - fh * 0.2)), int(min(vh - 1, fy + fh * 1.2))
    col = gx[r0:r1].mean(axis=0)                                  # сила вертикальных границ по столбцам
    def pick(arr, lo, hi):
        lo, hi = int(max(0, lo)), int(min(len(arr) - 1, hi))
        if hi - lo < 3: return None
        seg = arr[lo:hi]; i = int(np.argmax(seg))
        return lo + i if seg[i] > 3.0 * (np.median(arr) + 1e-3) else None
    L = pick(col, fx - 4 * fw, fx - 0.4 * fw); R = pick(col, fx + 1.4 * fw, fx + 5 * fw)
    if L is None: L = box[0]
    if R is None: R = box[0] + box[2]
    row = gy[:, int(L):int(R)].mean(axis=1)
    T = pick(row, fy - 3 * fh, fy - 0.3 * fh); B = pick(row, fy + 1.3 * fh, fy + 4.5 * fh)
    if T is None: T = box[1]
    if B is None: B = box[1] + box[3]
    L, R, T, B = int(L) + 2, int(R) - 1, int(T) + 2, int(B) - 1     # без самой рамки
    if R - L < fw * 1.5 or B - T < fh * 1.3: return box
    w, h = R - L, B - T; tw = h * W / TOP_H                          # подгоняем под пропорцию верха (cover)
    if tw < w: L += int((w - tw) / 2); w = int(tw)
    else: th = w * TOP_H / W; T += int((h - th) / 2); h = int(th)
    return (L, T, w, h)


def plan(video, vw, vh, t0, t1, mode='auto', cam=None):
    """Возвращает dict: layout + прямоугольники вырезки."""
    if vw / vh <= 9 / 16 + 0.01:                      # уже вертикальное
        return {'layout': 'vertical'}
    # В auto не пытаемся выводить наличие веб-камеры только из факта обнаружения лица:
    # игровые персонажи, постеры и элементы интерфейса часто дают ложные срабатывания.
    # Для стримов с вебкой оставлен отдельный режим split с поиском камеры.
    if mode == 'auto' and cam is None or mode == 'game' and cam is None:
        bx, by, bw, bh = content_bounds(video, vw, vh)
        side = min(bw, bh)
        sx = int(np.clip(bx + (bw-side)//2, bx, bx+bw-side))
        sy = by + (bh-side)//2
        return {'layout': 'game', 'square': (sx, sy, side, side),
                'default_x': sx, 'content': (bx, by, bw, bh)}
    auto, cam_box, face_x, face_y, face_h = 'fit', None, None, None, None
    if cam:
        auto, cam_box = 'split', tuple(cam)
    else:
        faces = scan_faces(video, vw, vh, t0, t1)
        if faces:
            arr = np.array(faces, float); fx = arr[:, 0] + arr[:, 2] / 2; fy = arr[:, 1] + arr[:, 3] / 2
            cx, cy = np.median(fx), np.median(fy); fw, fh = np.median(arr[:, 2]), np.median(arr[:, 3])
            stable = np.sum((np.abs(fx - cx) < fw) & (np.abs(fy - cy) < fh)) >= max(3, 0.4 * len(arr))
            if not stable and len(arr) >= 0.4 * 40 * (t1 - t0 > 0) and fh >= 0.08 * vh:
                auto, face_x, face_y, face_h = 'face', cx, cy, fh      # фильм: лица есть, но скачут по планам — кадр поведёт shot_track
            if stable:
                face_x, face_y, face_h = cx, cy, fh
                if fh < 0.28 * vh:                       # маленькое стабильное лицо = вебка поверх игры
                    ch = min(vh, fh * 2.7); cw = min(vw, ch * W / TOP_H)
                    cam_box = (int(np.clip(cx - cw / 2, 0, vw - cw)), int(np.clip(cy - ch * 0.45, 0, vh - ch)), int(cw), int(ch))
                    cam_box = refine_cam(video, vw, vh, t0, t1, cam_box, (cx - fw / 2, cy - fh / 2, fw, fh))
                    auto = 'split'
                    if cam_box[2] > 0.45 * vw:            # «рамка» почти на весь кадр — это не вебка, а сцена-общение
                        cam_box, auto = None, 'face'
                else:
                    auto = 'face'
            if auto == 'fit' and len(arr) >= 10 and fh >= 0.05 * vh:   # люди в кадре (студия, общение) — на весь экран,
                auto, face_x, face_y, face_h = 'face', cx, cy, fh      # а не на размытом фоне; говорящего найдёт shot_track
    layout = auto if mode == 'auto' else mode
    if layout == 'split' and cam_box is None: layout = 'fit'
    if layout == 'face' and face_x is None: face_x, face_y, face_h = vw / 2, vh / 2, vh / 4
    if cam_box:
        x, y, w, h = cam_box
        if not cam:                                  # чуть приближаем вебку, как в нарезках: лицо крупнее
            z = 1.12; nw, nh = int(w / z), int(h / z); x += (w - nw) // 2; y += int((h - nh) * 0.35); w, h = nw, nh
    if layout == 'face': x = face_x
    p = {'layout': layout}
    if layout == 'split':
        p['cam'] = (x // 2 * 2, y // 2 * 2, w // 2 * 2, h // 2 * 2)
        gw = min(vw, int(vh * W / BOT_H)) // 2 * 2       # игра: вырезка с пропорцией нижней части
        gh = min(vh, int(gw * BOT_H / W)) // 2 * 2
        cx0 = x + w / 2                                   # сдвигаем от вебки, чтобы она не попала в низ
        gx = (vw - gw) // 2                               # по центру экрана — там прицел и действие
        if gx < x + w and x < gx + gw and y < vh * 0.75:  # задевает вебку — сдвигаем в сторону от неё
            gx = max(0, x - gw) if cx0 > vw / 2 else min(vw - gw, x + w)
        p['game'] = (gx // 2 * 2, ((vh - gh) // 2) // 2 * 2, gw, gh)
    if layout == 'face':                                   # 9:16 вокруг лица; если человек далеко — приближаем
        ch = int(min(vh, max(face_h * 4.2, vh * 0.85))) // 2 * 2; cw = int(ch * 9 / 16) // 2 * 2
        cy0 = int(np.clip(face_y - ch * 0.4, 0, vh - ch))
        p['crop'] = (int(np.clip(x - cw / 2, 0, vw - cw)) // 2 * 2, cy0 // 2 * 2, cw, ch)
    return p


def filter_graph(p, bg_input=None):
    """filter_complex, выход [base] 1080x1920 (или 1920x1080 для layout=wide). bg_input — индекс входа с фоном для низа (split)."""
    L = p['layout']
    if L == 'wide':
        return '[0:v]scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1[base]'

    if L == 'vertical':
        return f'[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1[base]'
    if L == 'face':
        x, y, w, h = p['crop']
        if p.get('shots'):                                     # фильмы: своё положение кадра на каждую склейку
            ex = str(p['shots'][-1][1])
            for t, sx in reversed(p['shots'][:-1]): ex = f'if(lt(t,{p["shots"][p["shots"].index((t, sx)) + 1][0]:.2f}),{sx},{ex})'
            x = f"'{ex}'"
        return f'[0:v]crop={w}:{h}:{x}:{y},scale={W}:{H}:flags=lanczos,setsar=1[base]'
    if L == 'game':
        x, y, side, _ = p['square']
        expr = _track_expr(p.get('motion'), p.get('default_x', (side and x) or 0))
        bx, by, bw, bh = p.get('content', (0, 0, 0, 0))
        bgcrop = f'crop={bw}:{bh}:{bx}:{by},' if bw and bh else ''
        return (f'[0:v]split[a][b];'
                f'[a]{bgcrop}scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},boxblur=30:2,eq=brightness=-0.12[bg];'
                f"[b]crop={side}:{side}:x='{expr}':y={y},scale={W}:{W}:flags=lanczos[fg];"
                f'[bg][fg]overlay=0:(H-h)/2,setsar=1[base]')
    if L == 'split':
        x, y, w, h = p['cam']
        top = f'[0:v]crop={w}:{h}:{x}:{y},scale={W}:{TOP_H}:flags=lanczos,setsar=1[top]'
        if bg_input is not None:
            bot = f'[{bg_input}:v]scale={W}:{BOT_H}:force_original_aspect_ratio=increase,crop={W}:{BOT_H},setsar=1[bot]'
            return f'{top};{bot};[top][bot]vstack=2[base]'
        gx, gy, gw, gh = p['game']
        return (f'[0:v]split[a][b];' + top.replace('[0:v]', '[a]') +
                f';[b]crop={gw}:{gh}:{gx}:{gy},scale={W}:{BOT_H}:flags=lanczos,setsar=1[bot];[top][bot]vstack=2[base]')
    # fit: размытый фон + видео целиком
    return (f'[0:v]split[a][b];[a]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},boxblur=28:2,eq=brightness=-0.12[bg];'
            f'[b]scale={W}:-2:flags=lanczos[fg];[bg][fg]overlay=0:(H-h)/2,setsar=1[base]')


def caption_y(p):
    """Где ставить субтитры: на стыке в split, иначе на 68 % высоты."""
    return TOP_H if p['layout'] == 'split' else int(H * (0.70 if p['layout'] == 'game' else 0.68))


def shot_track(video, vw, vh, s, d, crop, max_shots=40, beat=3.0):
    """Монтажные склейки внутри куска (фильмы, эдиты) и центр лица в каждом плане → [(t_начала_плана, x_вырезки)].
    Кадр 9:16 «переезжает» к говорящему на каждой склейке, а не стоит по среднему лицу всего куска.
    Длинный план без склеек (студия, общение) режется на отрезки по beat секунд: кадр перескакивает на того,
    кто сейчас говорит, — как монтажёр нарезок."""
    import re, subprocess
    try:
        import cv2
        det = finder(); cap = _open(video)
    except Exception:
        return None
    r = subprocess.run(['ffmpeg', '-v', 'info', '-ss', f'{s:.3f}', '-t', f'{d:.3f}', '-i', video, '-an', '-vf',
                        "scale=320:-2,select='gt(scene,0.30)',showinfo", '-f', 'null', '-'], capture_output=True)
    real = sorted({0.0, d, *(t for t in map(float, re.findall(rb'pts_time:([0-9.]+)', r.stderr)[:max_shots]) if 0.0 < t < d)})   # без повторов: иначе два плана с одним t
    cuts = []
    for a_, b_ in zip(real, real[1:]):
        k = max(1, int((b_ - a_) // beat)); cuts += [a_ + (b_ - a_) * j / k for j in range(k)]
    cw = crop[2]; out = []; prev = crop[0]
    for i, t0 in enumerate(cuts):
        t1 = cuts[i + 1] if i + 1 < len(cuts) else d
        xs = []
        for t in np.linspace(t0 + 0.1, max(t0 + 0.15, t1 - 0.6), 2):     # кто говорит: у кого сильнее движется рот
            frames = []; first = None
            for dt in (0.0, 0.12, 0.24, 0.36):
                cap.set(cv2.CAP_PROP_POS_MSEC, (s + float(t) + dt) * 1000); ok, fr = cap.read()
                if ok:
                    sm = cv2.resize(fr, (vw // 2, vh // 2)); first = sm if first is None else first
                    frames.append(cv2.cvtColor(sm, cv2.COLOR_BGR2GRAY).astype(np.float32))
            if len(frames) < 2: continue
            fs = [f for f in det.find(first, vh // 24) if f[2] > 0 and f[3] > 0]
            if not len(fs): continue
            def talk(f):
                fx, fy, fw, fh = [max(0, v) for v in f]; m = [fr_[fy + fh // 2:fy + fh, fx:fx + fw] for fr_ in frames]
                if not m[0].size: return 0.0
                return float(np.mean([np.abs(a - b).mean() for a, b in zip(m, m[1:])])) * (1 + 0.15 * fw / max(x[2] for x in fs))
            fx, fy, fw, fh = max(fs, key=talk); xs.append((fx + fw / 2) * 2)
        x = int(np.clip(np.median(xs) - cw / 2, 0, vw - cw)) // 2 * 2 if xs else prev
        hard = any(abs(t0 - c) < 0.01 for c in real)              # на настоящей склейке переезжаем всегда,
        if not out or abs(x - out[-1][1]) > (4 if hard else cw * 0.35): out.append((round(t0, 2), x))   # внутри плана — только к другому человеку
        prev = x
    cap.release()
    return out if len(out) > 1 else None
