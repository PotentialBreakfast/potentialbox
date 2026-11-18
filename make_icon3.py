from PIL import Image, ImageDraw, ImageFont
size = 256
img = Image.new("RGBA", (size, size), (10, 10, 12, 255))
d = ImageDraw.Draw(img)
# subtle grid
for i in range(5):
    x = 20 + i*54
    d.line([(x,20),(x,size-20)], fill=(30,30,34), width=1)
    d.line([(20,x),(size-20,x)], fill=(30,30,34), width=1)
# PB text
try:
    font = ImageFont.truetype("arialbd.ttf", 150)
except:
    font = ImageFont.load_default()
text = "PB"
bbox = d.textbbox((0,0), text, font=font)
tw, th = bbox[2]-bbox[0], bbox[3]-bbox[1]
x = (size - tw)//2 - bbox[0]
y = (size - th)//2 - bbox[1]
d.text((x,y), text, font=font, fill=(245,245,245))
# accent underline
d.rectangle((x, y+th+6, x+tw, y+th+10), fill=(79,224,138))
img.save("potentialbox.ico", format="ICO", sizes=[(256,256),(128,128),(64,64),(32,32),(16,16)])
print("saved")
