import MarkdownIt from 'markdown-it'
import DOMPurify from 'dompurify'
import { createHighlighter, type Highlighter } from 'shiki'

// themes can be found in https://shiki.style/themes
export const CODE_HIGHLIGHTER_OPTIONS = ['kanagawa-dragon', 'nord', 'one-dark-pro']
export type CodeHighlighterOption = (typeof CODE_HIGHLIGHTER_OPTIONS)[number]

let highlighter: Highlighter | null = null

function escapeHtml(value: string): string {
	return value.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;')
}

export async function initHighlighter(): Promise<void> {
	highlighter = await createHighlighter({
		themes: CODE_HIGHLIGHTER_OPTIONS,
		langs: ['bash', 'json', 'log', 'python', 'yaml', 'ts', 'js', 'rust', 'c++', 'vue'],
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
					return highlighter.codeToHtml(code, { lang, theme: codeHighlighter })
				} catch {
					// fallback
				}
			}

			return `<pre><code>${escapeHtml(code)}</code></pre>`
		},
	})
}

export function renderMarkdown(md: MarkdownIt, content: string): string {
	const raw = md.render(content)
	return DOMPurify.sanitize(raw)
}
