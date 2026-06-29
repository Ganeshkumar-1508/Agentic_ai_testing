const fs = require('fs');
const raw = fs.readFileSync(__dirname + '/raw_stream.txt', 'utf8');
const lines = raw.split(/\r?\n/).filter(l => l.trim());
const events = lines.map(line => ({ t: new Date().toISOString(), line }));
const session_id = 'f25887e6-562b-40dc-99fc-416da4e657ef';
fs.writeFileSync(__dirname + '/delegate_stream.json',
  JSON.stringify({ session_id, event_count: events.length, stream_error: '', events }, null, 2));
console.log('Wrote ' + events.length + ' events to delegate_stream.json');
