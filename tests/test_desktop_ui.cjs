const { chromium } = require('playwright');
const { execFileSync } = require('child_process');
const fs = require('fs');
const path = require('path');
const os = require('os');
const project = path.resolve(__dirname, '..');
const fixture = fs.mkdtempSync(path.join(os.tmpdir(), 'publisher-ui-'));
execFileSync('python', ['-c', `
import json
from pathlib import Path
from PIL import Image
root=Path(${JSON.stringify(fixture)})
(root/'site/src/data').mkdir(parents=True)
(root/'site/package.json').write_text('{}')
(root/'site/src/data/photos.json').write_text('[]')
e=Image.Exif();e[272]='Sony ILCE-6700';e[0x8769]={36867:'2026:09:23 17:42:00',34855:200,42036:'56mm F1.7'}
Image.new('RGB',(800,500),(80,100,130)).save(root/'test.jpg',exif=e)
`]);
let validationMode='success';
let photoRequests=[];
(async () => {
  const browser=await chromium.launch({headless:true, executablePath:process.env.PUBLISHER_TEST_CHROME || undefined,args:['--no-sandbox']});
  const page=await browser.newPage({viewport:{width:1100,height:800}});
  const errors=[];page.on('pageerror',e=>errors.push(String(e)));
  await page.exposeFunction('nativeInvoke',async (cmd,args={})=>{
    if(cmd==='get_config')return {project:fixture+'/site',vault:fixture,webpEnabled:true};
    if(cmd==='get_python_info')return {available:true,executable:'python',version:'Python 3',publisherReady:true};
    if(cmd==='plugin:event|listen')return 1;
    if(cmd==='plugin:event|unlisten')return null;
    if(cmd==='validate_paths') {if(validationMode==='error')throw new Error('模拟验证调用失败');return [];}
    if(cmd==='plugin:dialog|open')return [fixture+'/test.jpg'];
    if(cmd==='photo_request'){
      photoRequests.push(args.payload.action);
      if(args.payload.action==='preview')return {url:'http://127.0.0.1:4321/photos/',message:'预览已生成'};
      if(args.payload.action==='publish')return {message:'照片修改已推送'};
      // Live python bridge: import must finish from the final result alone
      // (no photo-event progress lines reach this stubbed harness).
      // PYTHONUTF8=1 mirrors main.rs — without it Windows decodes stdin as GBK
      // and every CJK title written through this stub turns into mojibake.
      const output=execFileSync('python',['-m','publisher.cli','photos','--project',fixture+'/site'],{cwd:project,input:JSON.stringify(args.payload),encoding:'utf8',env:{...process.env,PYTHONUTF8:'1'}});
      const lines=output.trim().split('\n').map(l=>JSON.parse(l));
      const terminal=lines.filter(l=>l.type!=='photo_progress').pop();
      if(!terminal)throw new Error('photo bridge returned no terminal line');
      if(terminal.type==='error')throw new Error(terminal.message);return terminal.result;
    }
    if(cmd==='open_preview')return null;
    throw new Error('Unexpected command '+cmd);
  });
  await page.addInitScript(()=>{
    window.__TAURI_INTERNALS__={invoke:(cmd,args)=>window.nativeInvoke(cmd,args),transformCallback:()=>1};
    window.__TAURI_EVENT_PLUGIN_INTERNALS__={unregisterListener:()=>{}};
  });
  await page.goto('http://127.0.0.1:1420');
  await page.getByRole('button',{name:'Settings',exact:true}).click();
  await page.getByRole('button',{name:'验证路径',exact:true}).click();
  await page.getByRole('status').filter({hasText:'路径验证通过'}).waitFor();
  validationMode='error';
  await page.getByRole('button',{name:'验证路径',exact:true}).click();
  await page.getByRole('status').filter({hasText:'模拟验证调用失败'}).waitFor();
  await page.getByRole('button',{name:'摄影管理',exact:true}).click();
  await page.getByText('GPS 地点识别').waitFor();
  await page.waitForFunction(()=>!document.querySelector('.photo-status .spin'));
  await page.getByRole('button',{name:'选择一组照片'}).click();
  await page.getByText('本次导入 · 1 张').waitFor();
  // 单张导入：不出现组标题字段，直接保存。
  if(await page.getByLabel('整组标题').count())throw new Error('single import must not ask for a group title');
  await page.getByRole('button',{name:/test\.jpg/}).click();
  await page.getByAltText('选中照片预览').waitFor();
  if(await page.getByLabel('拍摄日期').inputValue()!=='2026-09-23')throw new Error('date metadata lost');
  if(await page.getByLabel('拍摄时间').inputValue()!=='17:42')throw new Error('minute metadata lost');
  await page.getByLabel('单张标题（留空沿用组规则）').fill('码头傍晚');
  await page.getByRole('button',{name:'保存到本地',exact:true}).click();
  await page.getByText('照片库 · 1 组 · 1 张').waitFor();
  // 组→照片两级导航：先展开组，再按 HH:mm 选中子照片（有标题的子行不显示“单张”徽标）。
  await page.getByRole('button',{name:'展开 码头傍晚',exact:true}).click();
  await page.getByRole('button',{name:/17:42/}).last().click();
  await page.getByLabel('单张标题（留空沿用组规则）').fill('单张标题');
  await page.getByRole('button',{name:'保存单张修改'}).click();
  await page.waitForFunction(()=>!document.querySelector('.photo-status .spin'));
  await page.getByRole('button',{name:'隐藏单张',exact:true}).click();
  await page.getByRole('button',{name:'取消单张隐藏',exact:true}).waitFor();
  await page.getByRole('button',{name:'取消单张隐藏',exact:true}).click();
  await page.getByRole('button',{name:'隐藏单张',exact:true}).waitFor();
  await page.getByRole('button',{name:'生成本地预览'}).click();
  await page.waitForFunction(()=>!document.querySelector('.photo-status .spin'));
  if(await page.getByRole('button',{name:'确认并提交上线'}).isDisabled())throw new Error('publish not enabled after preview');
  await page.screenshot({path:path.join(process.env.RUNNER_TEMP || os.tmpdir(),'publisher-photo-ui.png'),fullPage:true});
  const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>window.innerWidth);
  if(overflow)throw new Error('horizontal overflow');
  if(errors.length)throw new Error(errors.join('\n'));
  console.log(JSON.stringify({ok:true,photoRequests}));
  await browser.close();
  fs.rmSync(fixture,{recursive:true,force:true});
})().catch(e=>{console.error(e);process.exit(1)});
