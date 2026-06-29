const fs = require('fs');
const c = fs.readFileSync('src/app/(dashboard)/settings/page.tsx', 'utf8');
const tabs = [...c.matchAll(/value="([^"]+)"/g)];
console.log('Settings tabs:');
tabs.forEach(t => console.log(' ', t[1]));
const panels = [...c.matchAll(/<(\w+Panel)/g)];
const unique = [...new Set(panels.map(p => p[1]))];
console.log('\nPanel components used:');
unique.forEach(p => console.log(' ', p));
