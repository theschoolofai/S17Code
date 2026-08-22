const fs = require('fs');

async function check(file) {
  const html = fs.readFileSync(file, 'utf8');
  if (!html.includes('<title>Shannon AI | Sana 2.5 Flash</title>')) throw new Error('Missing title');
  if (!html.includes('startTimer')) throw new Error('Missing startTimer function');
  if (!html.includes('localStorage')) throw new Error('Missing localStorage');
  console.log('Webcheck passed');
}

check(process.argv[2]).catch(e => { console.error(e); process.exit(1); });