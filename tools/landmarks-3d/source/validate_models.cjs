// npm install gltf-validator @gltf-transform/core @gltf-transform/extensions draco3dgltf; node source/validate_models.cjs
const fs=require('fs'),path=require('path'),crypto=require('crypto');
const validator=require(process.env.GLTF_VALIDATOR_MODULE||'gltf-validator');
const {NodeIO}=require('@gltf-transform/core');
const {ALL_EXTENSIONS}=require('@gltf-transform/extensions');
const draco=require('draco3dgltf');
const root=path.resolve(__dirname,'..');
(async()=>{
  const manifest=JSON.parse(fs.readFileSync(path.join(root,'models/manifest.json'),'utf8'));
  const results=[];
  const io=new NodeIO().registerExtensions(ALL_EXTENSIONS).registerDependencies({'draco3d.decoder':await draco.createDecoderModule()});
  for(const model of manifest.models){
    const filename=path.join(root,'models',model.id+'.glb'),bytes=fs.readFileSync(filename);
    const result=await validator.validateBytes(new Uint8Array(bytes),{uri:model.id+'.glb',maxIssues:100});
    const json=JSON.parse(bytes.subarray(20,20+bytes.readUInt32LE(12)).toString('utf8'));
    const external=[...(json.buffers||[]),...(json.images||[])].filter(x=>x.uri&&!x.uri.startsWith('data:'));
    const document=await io.readBinary(new Uint8Array(bytes));
    document.getRoot().listExtensionsUsed().find(e=>e.extensionName==='KHR_draco_mesh_compression')?.dispose();
    const decoded=await io.writeBinary(document);
    const decodedResult=await validator.validateBytes(decoded,{uri:model.id+'-decoded.glb',maxIssues:100});
    results.push({id:model.id,bytes:bytes.length,sha256:crypto.createHash('sha256').update(bytes).digest('hex'),errors:result.issues.numErrors,warnings:result.issues.numWarnings,info:result.issues.numInfos,externalResources:external.length,extensions:json.extensionsUsed,issues:result.issues.messages,decoded:{errors:decodedResult.issues.numErrors,warnings:decodedResult.issues.numWarnings,issues:decodedResult.issues.messages}});
  }
  const output={validator:validator.version(),date:'2026-10-29',totalBytes:results.reduce((s,r)=>s+r.bytes,0),models:results};
  fs.writeFileSync(path.join(root,'validation.json'),JSON.stringify(output,null,2)+'\n');
  console.log(JSON.stringify(output,null,2));
  if(results.some(r=>r.errors||r.externalResources||r.decoded.errors))process.exitCode=1;
})();
