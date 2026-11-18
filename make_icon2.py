from PIL import Image, ImageDraw, ImageFilter
size = 256
img = Image.new("RGBA", (size, size), (10, 12, 18, 255))
d = ImageDraw.Draw(img)
# background gradient
for y in range(size):
    t = y / size
    r = int(10 + 8*t)
    g = int(12 + 10*t)
    b = int(18 + 14*t)
    d.line([(0,y),(size,y)], fill=(r,g,b))
# pad grid
pad = 44
gap = 10
start = (size - (4*pad + 3*gap))//2
for r in range(4):
    for c in range(4):
        x = start + c*(pad+gap)
        y = start + r*(pad+gap)
        # outer glow
        d.rounded_rectangle((x-2, y-2, x+pad+2, y+pad+2), radius=10, fill=(79,224,138,40))
        d.rounded_rectangle((x, y, x+pad, y+pad), radius=8, fill=(28,32,40), outline=(79,224,138), width=2)
        cx, cy = x+pad//2, y+pad//2
        # led
        color = (79,224,138) if (r+c)%2==0 else (242,163,58)
        d.ellipse((cx-5, cy-5, cx+5, cy+5), fill=color)
# knob bottom center
kx, ky = size//2, start + 4*(pad+gap) + 30
d.ellipse((kx-22, ky-22, kx+22, ky+22), fill=(20,24,32), outline=(242,163,58), width=3)
d.line((kx, ky-16, kx, ky+16), fill=(79,224,138), width=3)
# top highlight
d.ellipse((kx-6, ky-16, kx+6, ky-10), fill=(255,255,255,80))
img.save("potentialbox.ico", format="ICO", sizes=[(256,256),(128,128),(64,64),(32,32),(16,16)])
print("saved")
