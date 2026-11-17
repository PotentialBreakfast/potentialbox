from PIL import Image, ImageDraw
size = 256
img = Image.new("RGBA", (size, size), (18, 20, 26, 255))
d = ImageDraw.Draw(img)
# grid of pads
pad = 46
gap = 12
start = (size - (4*pad + 3*gap))//2
for r in range(4):
    for c in range(4):
        x = start + c*(pad+gap)
        y = start + r*(pad+gap)
        # pad body
        d.rounded_rectangle((x, y, x+pad, y+pad), radius=8, fill=(40,44,52), outline=(70,76,86), width=2)
        # led dot
        cx, cy = x+pad//2, y+pad//2
        d.ellipse((cx-6, cy-6, cx+6, cy+6), fill=(79,224,138) if (r+c)%2==0 else (242,163,58))
# knobs row at bottom
ky = start + 4*(pad+gap) + 12
for i in range(4):
    kx = start + i*(pad+gap) + pad//2
    d.ellipse((kx-14, ky-14, kx+14, ky+14), fill=(24,28,36), outline=(79,224,138), width=2)
    d.line((kx, ky-10, kx, ky+10), fill=(242,163,58), width=2)
img.save("potentialbox.ico", format="ICO", sizes=[(256,256),(128,128),(64,64),(32,32),(16,16)])
print("saved")
