const fs = require('fs');
const data = JSON.parse(fs.readFileSync('/root/.hermes/cron/output/innovation_projects_sent.json', 'utf8'));
if (!data.projects) data.projects = [];
if (!data.projects.some(p => p.name.toLowerCase() === 'worldmonitor')) {
  data.projects.push({ name: 'WorldMonitor', url: 'https://github.com/koala73/worldmonitor', sent_at: new Date().toISOString() });
  fs.writeFileSync('/root/.hermes/cron/output/innovation_projects_sent.json', JSON.stringify(data, null, 2));
  console.log('Added WorldMonitor to sent list');
} else {
  console.log('Already in sent list');
}
