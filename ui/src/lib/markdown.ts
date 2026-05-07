import MarkdownIt from 'markdown-it'
import DOMPurify from 'dompurify'
import { createHighlighter, type Highlighter } from 'shiki'

// themes can be found in https://shiki.style/themes
export const CODE_HIGHLIGHTER_OPTIONS = ['kanagawa-dragon', 'nord', 'one-dark-pro']
export type CodeHighlighterOption = (typeof CODE_HIGHLIGHTER_OPTIONS)[number]

let highlighter: Highlighter | null = null

function normalizeLanguageLabel(lang: string): string {
	const normalized = (lang || '').trim().toLowerCase()
	if (!normalized) return 'text'

	const labels: Record<string, string> = {
		js: 'javascript',
		ts: 'typescript',
		yml: 'yaml',
		sh: 'shell',
		zsh: 'shell',
		bash: 'bash',
		plaintext: 'text',
		text: 'text',
		txt: 'text',
		conf: 'config',
		cfg: 'config',
		ini: 'config',
	}

	return labels[normalized] ?? normalized
}

function wrapCodeBlock(content: string, lang: string): string {
	const label = normalizeLanguageLabel(lang)
	return [
		`<div class="code-block" data-code-lang="${escapeHtml(label)}">`,
		'<div class="code-block__header">',
		`<span class="code-block__lang">${escapeHtml(label)}</span>`,
		'<button type="button" class="code-block__copy" data-copy-code aria-label="Copy code">Copy</button>',
		'</div>',
		content,
		'</div>',
	].join('')
}

function escapeHtml(value: string): string {
	return value.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;')
}

export async function initHighlighter(): Promise<void> {
	highlighter = await createHighlighter({
		themes: CODE_HIGHLIGHTER_OPTIONS,
		langs: ['bash', 'shell', 'json', 'log', 'python', 'yaml', 'toml', 'ini', 'ts', 'js', 'rust', 'c++', 'vue'],
	})
}

export function createMarkdown(codeHighlighter: CodeHighlighterOption = 'kanagawa-dragon'): MarkdownIt {
	return new MarkdownIt({
		html: false,
		linkify: true,
		breaks: true,
		highlight(code: string, lang: string): string {
			if (highlighter && lang) {
				try {
					return wrapCodeBlock(
						highlighter.codeToHtml(code, { lang, theme: codeHighlighter }),
						lang
					)
				} catch {
					// fallback
				}
			}

			return wrapCodeBlock(`<pre><code>${escapeHtml(code)}</code></pre>`, lang)
		},
	})
}

export function renderMarkdown(md: MarkdownIt, content: string): string {
	const raw = md.render(content)
	return DOMPurify.sanitize(raw)
}
