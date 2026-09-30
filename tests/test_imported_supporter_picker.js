const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const test = require('node:test');

const source = fs.readFileSync('static/pages.js', 'utf8');
const picker = source.slice(source.indexOf('const setupImportedSupporterPicker='),
  source.indexOf('\nconst importedForms='));

test('split phone form autofills, switches people, and clears for manual entry', () => {
  const fields = Object.fromEntries([
    'name', 'name_english', 'name_yiddish', 'cell_phone', 'home_phone', 'email',
    'home_street', 'home_unit', 'work_company', 'work_street', 'mailing_preference',
    'relationship',
  ].map(name => [name, {value: '', readOnly: false}]));
  fields.relationship.value = 'Friend';
  const handlers = {};
  const select = {
    value: '1',
    replaceChildren(...options) { this.options = options; },
    addEventListener(event, handler) { handlers[event] = handler; },
  };
  const form = {querySelector(selector) {
    return fields[selector.match(/name="([^"]+)"/)[1]] || null;
  }};
  const profiles = [
    {id: 1, name: 'Moshe', english_name: 'Moshe', yiddish_name: 'משה',
     phone: '8451112222', cell_phone: '8451112222', home_phone: '8453334444',
     email: 'moshe@example.test', home: {street: '12 Main', unit: '2'},
     work: {street: '20 Work', company: 'Office'}, mailing_preference: 'home'},
    {id: 2, name: 'No phone', english_name: 'No phone'},
  ];
  const context = {form, profiles, select, Option: function(text, value) {
    this.textContent = text; this.value = value;
  }};
  vm.runInNewContext(picker + '\nsetupImportedSupporterPicker(form,profiles,{new:"New"},select);', context);
  assert.equal(fields.name_yiddish.value, 'משה');
  assert.equal(fields.cell_phone.value, '8451112222');
  assert.equal(fields.home_phone.value, '8453334444');
  assert.equal(fields.home_street.value, '12 Main');
  assert.equal(fields.work_company.value, 'Office');
  assert.equal(fields.name_english.readOnly, true);
  assert.equal(fields.relationship.value, 'Friend');
  select.value = '2'; handlers.change();
  assert.equal(fields.name.value, 'No phone');
  for (const name of ['cell_phone', 'home_phone', 'email', 'home_street', 'work_company'])
    assert.equal(fields[name].value, '');
  select.value = ''; handlers.change();
  assert.equal(fields.name.value, '');
  assert.equal(fields.name_english.readOnly, false);
});
