"""Re-theme HQ to the silenthelp.org look: neutral near-black surfaces, white accent.

Green-tinted colors become neutral grays of the same lightness (so contrast and
layering are preserved); the green accent family becomes white. Blue, amber and
red status colors are kept. Run once: python3 scripts/retheme.py
"""
import colorsys, re, sys

def to_rgb(h):
    h = h.lstrip('#')
    if len(h) in (3, 4): h = ''.join(c * 2 for c in h)
    a = h[6:8] if len(h) == 8 else ''
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)), a

def hexify(rgb, a=''):
    return '#' + ''.join(f'{round(max(0, min(1, c)) * 255):02x}' for c in rgb) + a

def neutral(rgb):
    r, g, b = rgb
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    hue = h * 360
    green_family = 55 <= hue <= 170
    if s < 0.08 or green_family:
        if green_family and l > 0.72 and s > 0.25:   # the sage accent family -> white
            return (1.0, 1.0, 1.0)
        # same lightness, no tint; very dark surfaces pulled toward the site's #010101 ground
        v = l * 0.92 if l < 0.12 else l
        return (v, v, v)
    return rgb  # blue / amber / red status colors keep their hue

def swap_hex(m):
    rgb, a = to_rgb(m.group(0))
    return hexify(neutral(rgb), a)

def swap_rgba(m):
    parts = [p.strip() for p in m.group(1).split(',')]
    r, g, b = (float(x) / 255 for x in parts[:3])
    nr = neutral((r, g, b))
    return 'rgba(' + ','.join(str(round(c * 255)) for c in nr) + (',' + parts[3] if len(parts) > 3 else '') + ')'

HEX = re.compile(r'#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b')
RGBA = re.compile(r'rgba?\(([^)]*)\)')

for path in sys.argv[1:]:
    s = open(path).read()
    s = HEX.sub(swap_hex, s)
    s = RGBA.sub(swap_rgba, s)
    open(path, 'w').write(s)
    print('re-themed', path)
