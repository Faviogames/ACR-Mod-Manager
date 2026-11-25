"""Developer worker: cook only explicit author PNGs into a private output directory."""
def main():
    import os,json
    from pathlib import Path
    import wr,tools.exporter.pipeline as pl
    w,a=wr._installs();os.environ.update(pl._env(w,a,a/'acr/Content/Paks'))
    import tools.acrmod.texture_writer as tw
    import wr_images
    root=Path(os.environ.get('ACR_CM_ART_BUILD_ROOT',str(wr.ROOT.parent)))
    plan=json.loads((root/'authored-plan.json').read_text(encoding='utf-8'))
    output=root/'authored-legacy/acr/Content'
    temporary=root/'authored-png';temporary.mkdir(exist_ok=True)
    for index,job in enumerate(plan):
        png=temporary/(str(index)+'.png')
        wr_images.fitted(job['source'],tuple(job['size'])).save(png)
        tw.write_texture(output,job['package'],image=str(png),fmt='B8G8R8A8',srgb=True,mips=False,
                         lod_group='TEXTUREGROUP_UI',compression='TC_EditorIcon',never_stream=True)
        print('Cooked authored UI:',job['package'],flush=True)
