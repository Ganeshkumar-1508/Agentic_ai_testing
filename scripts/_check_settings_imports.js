const fs = require('fs');
const c = fs.readFileSync('src/app/(dashboard)/settings/page.tsx', 'utf8');
const lines = c.split('\n');
console.log('=== IMPORTS ===');
lines.forEach((l, i) => {
  if (l.includes('import ')) console.log((i+1) + ': ' + l.trim());
});
console.log('\n=== TabsContent values ===');
lines.forEach((l, i) => {
  const m = l.match(/value="([^"]+)"[\s\S]{0,200}?(<[A-Z]\w+|<\w+\.)/);
  if (l.includes('TabsContent')) console.log((i+1) + ': ' + l.trim());
});
