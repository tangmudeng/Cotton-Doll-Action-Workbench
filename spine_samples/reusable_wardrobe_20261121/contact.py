from build import *
ORIGINAL=ROOT/'spine_samples/video_motion_study_20261119/pixel_sync_20261120'
out=HERE/'fitted';data=read(out/'evaluated.json');sheet=Image.new('RGB',(192*3,240*5),'#f0f0f0')
(HERE/'frame_checks').mkdir(exist_ok=True)
for i in range(23):
    rowimage=Image.new('RGB',(384*3,480),'#f0f0f0')
    ref=Image.open(ORIGINAL/f'reference_frames/{i+63:04}.png').crop((248,0,632,480));rowimage.paste(ref,(0,0))
    for col,(name,frames) in enumerate(data.items(),1):
        canvas=np.zeros((480,384,4),np.float32)
        for g in frames[i]['meshes']:canvas=over(canvas,render(Image.open(out/'parts'/f'{g["path"]}.png'),g,1))
        rowimage.paste(Image.fromarray(rgb(canvas)),(col*384,0))
    rowimage.save(HERE/'frame_checks'/f'{i+63:04}.png')
    if i in [0,5,11,17,22]:sheet.paste(rowimage.resize((192*3,240)),(0,[0,5,11,17,22].index(i)*240))
sheet.save(HERE/'fitted_comparison.png');print('Rendered all 23 frames from official-runtime mesh positions.')
