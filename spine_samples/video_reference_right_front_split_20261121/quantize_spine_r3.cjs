// Spine 4.2 persists animation time to 4 decimals and transforms to 3-5.
// Quantize authored tracks before roundtrip so browser and Spine use the same motion.
const fs=require('fs'),path=require('path'),file=path.join(__dirname,'candidate_r3','skin.json'),raw=JSON.parse(fs.readFileSync(file));
for(const anim of Object.values(raw.animations))for(const channels of Object.values(anim.bones||{}))for(const [channel,keys] of Object.entries(channels))for(const key of keys)for(const [k,v] of Object.entries(key))if(typeof v==='number')key[k]=Number(v.toFixed(k==='time'?4:channel==='scale'?3:2));
fs.writeFileSync(file,JSON.stringify(raw,null,2));console.log('Quantized Spine bone keys before computing deform residuals.');
