"""Exercise the generated-page click handler without calling Gemini."""
import ast
import json
from pathlib import Path
import shutil
import subprocess
import unittest


@unittest.skipUnless(shutil.which('node'), 'Node.js is required for JavaScript checks')
class FollowLinksTests(unittest.TestCase):
    def test_generated_destinations_and_local_controls(self):
        source = Path(__file__).resolve().parents[1] / 'main.py'
        tree = ast.parse(source.read_text())
        function = next(
            node for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == 'get_follow_links_script'
        )
        namespace = {}
        exec(compile(ast.Module(body=[function], type_ignores=[]), str(source), 'exec'), namespace)
        page_id = 'a' * 64
        script = namespace['get_follow_links_script'](page_id)
        script = script.removeprefix('<script>').removesuffix('</script>\n')
        harness = r'''
const assert = require('node:assert/strict');
const vm = require('node:vm');
const cases = [
  {name: 'friend profile fragment', href: '#friend-jenny', kind: 'profile', follow: true},
  {name: 'untyped fictional fragment', href: '#rave-archive', follow: true},
  {name: 'placeholder content link', href: '#', kind: 'related', follow: true},
  {name: 'typed link without href', href: '', kind: 'magazine', follow: true},
  {name: 'relative destination', href: 'articles/music.html', follow: true},
  {name: 'blank target destination', href: 'https://fictional.example/page', target: '_blank', follow: true},
  {name: 'real section', href: '#about', ids: ['about'], follow: false},
  {name: 'encoded section', href: '#about%20me', ids: ['about me'], follow: false},
  {name: 'named anchor', href: '#top', names: ['top'], follow: false},
  {name: 'UI control', href: '#add-friend', kind: 'ui', follow: false},
  {name: 'email link', href: 'mailto:editor@example.com', follow: false},
  {name: 'phone link', href: 'tel:123', follow: false},
  {name: 'script control', href: 'javascript:void(0)', follow: false},
  {name: 'no destination or kind', href: '', follow: false},
  {name: 'outside generated page', href: '/', outside: true, follow: false},
];
for (const item of cases) {
  let handler, capture, destination, prevented = false, stopped = false;
  const link = {
    dataset: {linkKind: item.kind}, target: item.target || '', textContent: 'Jenny',
    getAttribute: name => name === 'href' ? item.href : null,
    closest: () => item.outside ? null : {},
  };
  const document = {
    addEventListener: (type, callback, useCapture) => {
      assert.equal(type, 'click'); handler = callback; capture = useCapture;
    },
    getElementById: id => (item.ids || []).includes(id) ? {} : null,
    getElementsByName: name => (item.names || []).includes(name) ? [{}] : [],
  };
  vm.runInNewContext(SCRIPT, {
    document, URLSearchParams, window: {location: {assign: url => destination = url}},
  });
  handler({
    target: {closest: () => link},
    preventDefault: () => prevented = true,
    stopImmediatePropagation: () => stopped = true,
  });
  assert.equal(capture, true, item.name);
  assert.equal(Boolean(destination), item.follow, item.name);
  assert.equal(prevented, item.follow, item.name);
  assert.equal(stopped, item.follow, item.name);
  if (item.follow) {
    const url = new URL(destination, 'http://localhost');
    assert.equal(url.pathname, '/follow', item.name);
    assert.equal(url.searchParams.get('parent'), PAGE_ID, item.name);
    assert.equal(url.searchParams.get('label'), 'Jenny', item.name);
    assert.equal(url.searchParams.get('target'), item.href, item.name);
    assert.equal(url.searchParams.get('kind'), item.kind || 'related', item.name);
  }
}
console.log(`${cases.length} click-routing scenarios passed`);
'''
        result = subprocess.run(
            ['node', '-e', 'const SCRIPT = ' + json.dumps(script)
             + '; const PAGE_ID = ' + json.dumps(page_id) + ';\n' + harness],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
