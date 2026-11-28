#!/usr/bin/env node
// 编译真实的 HeroUI Pro 外壳；输出不依赖 CDN，可内联到离线 HTML。
import { execFileSync } from 'node:child_process'
import { mkdir, mkdtemp, readFile, readdir, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { build, transform } from 'esbuild'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const source = join(root, 'src')
const output = join(root, 'assets')

// 公共 PR 只做源码解析，不需要下载授权组件，也不执行应用代码。
if (process.argv.includes('--check')) {
  for (const entry of await readdir(source, { recursive: true })) {
    const loader = entry.endsWith('.jsx') ? 'jsx' : entry.endsWith('.js') ? 'js' : entry.endsWith('.css') ? 'css' : null
    if (loader) await transform(await readFile(join(source, entry), 'utf8'), { loader, sourcefile: entry })
  }
  await Promise.all(['shell.jsx', 'styles.css'].map(name => readFile(join(source, name))))
  console.log('✓ UI 源码语法检查通过（未解析授权组件依赖）')
} else {
  const temporary = await mkdtemp(join(tmpdir(), 'gctime-ui-'))
  try {
    const result = await build({
      absWorkingDir: root,
      entryPoints: ['src/shell.jsx'],
      outfile: 'assets/ui.js',
      bundle: true,
      format: 'iife',
      platform: 'browser',
      target: ['es2020'],
      jsx: 'automatic',
      minify: true,
      sourcemap: false,
      splitting: false,
      legalComments: 'inline',
      define: { 'process.env.NODE_ENV': '"production"' },
      write: false
    })
    if (result.outputFiles.length !== 1 || !result.outputFiles[0].path.endsWith('.js')) {
      throw new Error('UI 必须编译为单个 JavaScript 文件；样式统一放入 src/styles.css')
    }
    const stylesheet = join(temporary, 'ui.css')
    execFileSync(process.execPath, [
      join(root, 'node_modules/@tailwindcss/cli/dist/index.mjs'),
      '--input', join(source, 'styles.css'), '--output', stylesheet, '--minify'
    ], { cwd: root, stdio: 'inherit' })
    await mkdir(output, { recursive: true })
    await writeFile(join(output, 'ui.js'), result.outputFiles[0].contents)
    await writeFile(join(output, 'ui.css'), await readFile(stylesheet))
    console.log('✓ React / HeroUI Pro 已编译：assets/ui.js + assets/ui.css')
  } finally {
    await rm(temporary, { recursive: true, force: true })
  }
}
