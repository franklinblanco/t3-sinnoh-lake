from pathlib import Path
from PIL import Image, ImageChops, ImageDraw, ImageOps
from cruise import LakeTraffic, lit
import numpy as np
import math, struct, sys
from io import BytesIO

work = Path(__file__).parent
art = work.parent / 'assets'
sprites_dir = work / 'sprites'
assets = art / 'phases'
assets.mkdir(parents=True, exist_ok=True)
original = Image.open(art / "sinnoh-rift.png").convert("RGB")
W,H = original.size
import argparse
parser = argparse.ArgumentParser(description="Build one lake phase from the source artwork.")
parser.add_argument("phase", choices=["day", "night", *(
    f"{direction}{level}" for direction in ("rise", "set") for level in range(1, 9)
)])
parser.add_argument("--preview", type=Path, help="Save a still from the composed animation")
parser.add_argument("--frame", type=int, choices=range(240), metavar="0..239", default=0)
args = parser.parse_args()
phase = args.phase
mode, step = ("night",0) if phase=="night" else ("day",8) if phase=="day" else (phase[:-1],int(phase[-1]))
def mix(a,b,f):
    return a*(1-f) + b*f

def scene():
    src = np.asarray(original, dtype=np.float32)
    lum = src @ np.array([.24, .60, .16], dtype=np.float32)
    chroma = src - lum[..., None]
    x = (np.arange(W) + .5) / W
    y = (np.arange(H)[:, None] + .5) / H

    def grade(tones, saturation):
        # Map values separately from hue so brass leaves and teal water keep
        # their local colors even when they share the same brightness.
        values = [0, 32, 64, 96, 128, 160, 192, 224, 255]
        base = np.stack([np.interp(lum, values, channel)
                         for channel in zip(*tones)], axis=-1)
        return base + saturation * chroma

    def rgb(values):
        return Image.fromarray(np.uint8(np.clip(values, 0, 255)))

    daylight = src * [.84, .86, .88] + [3, 5, 7]
    if mode == 'day':
        return rgb(daylight)

    night = grade([(3, 8, 19), (8, 17, 31), (16, 27, 46),
                   (26, 38, 63), (37, 49, 78), (49, 60, 89),
                   (63, 73, 100), (81, 89, 113), (103, 109, 129)], .16)
    if mode == 'night':
        return rgb(night)

    morning = mode == 'rise'
    center = .448 if morning else .656
    sun_x = center + (.007 if morning else -.007) * (max(step, 4) - 5)
    ridge_height = .32 if morning else .40
    dawn = [(8, 16, 29), (26, 33, 50), (47, 54, 77), (74, 77, 99),
            (107, 99, 117), (149, 123, 131), (190, 151, 146),
            (223, 184, 162), (242, 213, 183)]
    dusk = [(12, 13, 30), (31, 29, 51), (55, 45, 69), (87, 61, 87),
            (121, 80, 101), (158, 103, 111), (196, 132, 121),
            (224, 166, 137), (245, 201, 156)]
    golden = grade(dawn if morning else dusk, .37)
    # Light pools low in the sky, catching cliff faces and the far trees.
    glow = np.exp(-((x - sun_x) / .30)**2 - ((y - ridge_height) / .145)**2)
    golden += glow[..., None] * ([80, 53, 22] if morning else [90, 49, 14])

    # Use the painted horizontal ripples for the brighter glints. The
    # reflection broadens towards the viewer and fades into the deep water.
    depth = np.clip((y - .54) / .36, 0, 1)
    surface = np.clip((y - .54) / .025, 0, 1) * (1 - depth)**1.5
    width = .018 + .075 * depth
    column = np.exp(-((x - sun_x) / width)**2) * surface
    # Compare nearby rows to isolate the fine reflected marks from the large
    # color fields of sky and forest already mirrored on the lake.
    ripple = np.clip((lum - np.roll(lum, 3, axis=0)) / 12, 0, 1)
    # A few sun-facing facets also catch light on the otherwise still open
    # water. Keep the ripple pattern stable as the sun moves along the ridge.
    facets = Image.new('L', (W, H))
    draw = ImageDraw.Draw(facets)
    rng = np.random.default_rng(214)
    for distance in np.linspace(.012, .90, 74)**1.45:
        row = round(H * (.54 + .36 * distance))
        spread = W * (.005 + .046 * distance)
        for offset in rng.normal(0, spread, 3):
            left = round((sun_x * W + offset) / 2) * 2
            length = round(rng.uniform(3, 9) * (1 + distance))
            draw.line((left, row, left + length, row),
                      fill=int(rng.integers(65, 190)), width=1 + int(distance > .22))
    glints = np.maximum(ripple, np.asarray(facets) / 255)
    golden += (column * (.19 + .81 * glints))[..., None] * [112, 79, 42]

    weight = [0, .13, .31, .54, .79, 1, .74, .43, .18][step]
    result = mix(night if step <= 5 else daylight, golden, weight)
    if step >= 4:
        # Trace the skyline around the two sun paths in source-pixel coordinates.
        if morning:
            ridge_x = [710, 717, 732, 744, 750, 760, 764, 772, 778, 786, 798, 812]
            ridge_y = [295, 297, 297, 295, 298, 308, 310, 316, 317, 324, 326, 334]
        else:
            ridge_x = [1036, 1048, 1054, 1063, 1070, 1078, 1084, 1096, 1104, 1110, 1124]
            ridge_y = [364, 369, 370, 375, 376, 379, 379, 375, 373, 369, 366]
        ridge = np.interp(np.arange(W), ridge_x, ridge_y)
        cx = round(sun_x * W)
        cy = ridge[cx] + {4: 8, 5: -5, 6: -25, 7: -54, 8: -92}[step]
        px = (np.arange(W) // 3 * 3)[None, :]
        py = (np.arange(H) // 3 * 3)[:, None]
        disc = ((px - cx)**2 + (py - cy)**2 < 19**2)
        # Clip each row against the ridge even within the sun's 3-pixel cells.
        sun = disc & (np.arange(H)[:, None] < ridge[None, :])
        result[sun] = mix(result[sun], np.array([255, 230, 174]), .90 if step <= 6 else .65)
    return rgb(result)


lake=scene()
traffic = LakeTraffic(lake, mode, step)
waters=(0,round(H*.55),W,round(H*.87))
water=lake.crop(waters).convert('RGBA')
swimmers=[(129,.32,.125,.669,57,.18),(129,.48,.079,.614,38,.84),(418,.68,.114,.738,59,.57),(456,.50,.142,.792,78,.38)]
def load_swimmer(species,width):
    gif=Image.open(sprites_dir/f'{species}.gif')
    frames=[]; ends=[]
    for i in range(gif.n_frames):
        gif.seek(i)
        frame=gif.convert('RGBA')
        # Register every frame to the opaque silhouette; the battle sprites contain jump
        # offsets and uneven transparent margins that would lift them above the wake.
        frame=frame.crop(frame.getbbox())
        if species==129:
            frame=frame.rotate(19,Image.Resampling.NEAREST,expand=True)
            frame=frame.crop(frame.getbbox())
        height=round(frame.height*width/frame.width*({129:.50,418:.84,456:.71}[species]))
        frame=frame.resize((width,height),Image.Resampling.NEAREST)
        frames.append(lit(frame, traffic.light))
        ends.append((ends[-1] if ends else 0)+gif.info.get("duration",100))
    return frames,ends
groups=[load_swimmer(s[0],s[4]) for s in swimmers]
def render(n):
    t=n/240
    sheet=water.copy()
    traffic.draw_boat(sheet, waters[1], t)
    for (species,center,radius,line,width,phase_offset),(frames,ends) in zip(swimmers,groups):
        angle=2*math.pi*(t+phase_offset)
        x=round(W*(center+radius*math.cos(angle)))
        y=round(H*(line+.012*math.sin(angle)))-waters[1]
        pos=(t*round(24000/ends[-1])+phase_offset)%1*ends[-1]
        frame=frames[next(i for i,end in enumerate(ends) if end>pos)]
        # Narrow the silhouette during a turn; both sides meet at the end of the path.
        span=round(width*(.52+.48*min(1,abs(math.sin(angle))*4)))
        stride=frame.resize((span,frame.height),Image.Resampling.NEAREST)
        direction=1 if math.sin(angle)<0 else -1
        if direction>0: stride=ImageOps.mirror(stride)
        hh=stride.height
        surface=int(hh*({129:.20,418:.49,456:.10}[species]))
        top=y-surface
        left=x-span//2
        under=sheet.crop((left,top,left+span,top+hh))
        # The lake texture shows through the submerged bodies. Only Buizel's head and
        # the crest of the larger Magikarp are clear of the surface.
        for row in range(hh):
            depth=(row-surface)/hh
            visibility= (.74 if depth<0 else max(.16,.52-.39*depth))
            if species==456: visibility=.43-.18*max(0,depth)
            strip=stride.crop((0,row,span,row+1))
            strip.putalpha(strip.getchannel("A").point(lambda a,s=visibility:round(a*s)))
            shift=round(math.sin(row*.52+12*angle)) if depth>0 else 0
            under.alpha_composite(strip,(shift,row))
        sheet.paste(under,(left,top))
        draw=ImageDraw.Draw(sheet)
        for k in range(3):
            p=(t*12+phase_offset+k/3)%1
            wake_x=round(x-direction*span*(.26+.58*p))
            wy=y+round(1+4*p)
            size=round(span*(.15-.10*p))+1
            shore=water.getpixel((wake_x,wy))[:3]
            opacity = (1 - p) * (.32 if species != 456 else .18)
            color = tuple(round(mix(c, 198 * light, opacity))
                          for c, light in zip(shore, traffic.light))
            draw.line((wake_x-size,wy,wake_x+size,wy),fill=color)
        # Foreground ripple crosses the sprite at its waterline.
        for start,end in [(-.34,-.15),(-.06,.21)]:
            wy=y+(1 if start<-.1 else 0)
            rgb=water.getpixel((x,wy))[:3]
            opacity = .31 if species != 456 else .21
            col = tuple(round(mix(c, 183 * light, opacity))
                        for c, light in zip(rgb, traffic.light))
            draw.line((round(x+start*span),wy,round(x+end*span),wy),fill=col,width=2)
    frame = lake.copy()
    frame.paste(sheet, waters[:2])
    traffic.sky(frame, t)
    return frame

if args.preview:
    render(args.frame).save(args.preview)
    sys.exit()

def chunk(tag,data):
    return tag+struct.pack("<I",len(data))+data+b"\0"*(len(data)%2)
def u24(n):return int(n).to_bytes(3,"little")
def encode(im,x=0,y=0):
    s=BytesIO(); im.save(s, "WEBP",lossless=True,method=2)
    blob=s.getvalue()[12:]; assert blob[:4]==b'VP8L'
    return chunk(b'ANMF',b''.join(map(u24,[x//2,y//2,im.width-1,im.height-1,100]))+b'\0'+blob)
body=bytearray(chunk(b'VP8X',bytes([18,0,0,0])+u24(W-1)+u24(H-1))+chunk(b'ANIM',bytes(6)))
prev=None
for n in range(240):
    frame = render(n)
    if prev is None:
        body.extend(encode(frame))
    else:
        diff = ImageChops.difference(frame, prev)
        left, top, right, bottom = diff.getbbox()
        # ANMF positions use two-pixel units. Unchanged pixels inside the
        # bounding box stay transparent between the sky and water layers.
        box = (left & ~1, top & ~1, right, bottom)
        patch = frame.crop(box)
        r, g, b = diff.crop(box).split()
        mask = ImageChops.lighter(r, ImageChops.lighter(g, b)).point(lambda v: 255 if v else 0)
        patch.putalpha(mask)
        body.extend(encode(patch, box[0], box[1]))
    prev = frame
out=assets/(phase+'.webp')
out.write_bytes(chunk(b'RIFF',b'WEBP'+body))
with Image.open(out) as check:
    assert check.n_frames==240 and check.info['loop']==0 and out.stat().st_size<16*1024*1024
    for n in [0,60,150,239]:
        check.seek(n)
        assert ImageChops.difference(check.convert('RGB'), render(n)).getbbox() is None
print(phase,out.stat().st_size,flush=True)
