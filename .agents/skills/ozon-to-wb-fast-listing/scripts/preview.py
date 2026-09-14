"""Create a numbered source-image contact sheet from image_manifest.json."""
import argparse,json,math
from pathlib import Path
from PIL import Image,ImageOps,ImageDraw

def preview(manifest,output):
    data=json.loads(Path(manifest).read_text(encoding='utf-8'))
    items=data['selected']; w,h=260,350; cols=4
    sheet=Image.new('RGB',(cols*w,math.ceil(len(items)/cols)*h),'white'); draw=ImageDraw.Draw(sheet)
    for i,item in enumerate(items):
        im=Image.open(item['file']).convert('RGB'); im.thumbnail((w-16,h-40))
        x,y=(i%cols)*w,(i//cols)*h
        sheet.paste(im,(x+(w-im.width)//2,y+24))
        draw.text((x+8,y+5),f"{i+1}  {item['width']}x{item['height']}",fill='black')
    sheet.save(output,quality=92)
    return str(Path(output).resolve())

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('manifest'); p.add_argument('output'); a=p.parse_args()
    print(preview(a.manifest,a.output))
