module.exports = {
	root: true,
	env: {
		browser: true,
		es2021: true,
		node: true,
	},
	extends: [
		'eslint:recommended',
		'plugin:vue/vue3-essential',
		'plugin:@typescript-eslint/recommended',
		'@vue/eslint-config-prettier/skip-formatting',
	],
	parser: 'vue-eslint-parser',
	parserOptions: {
		parser: '@typescript-eslint/parser',
		ecmaVersion: 'latest',
		sourceType: 'module',
		extraFileExtensions: ['.vue'],
	},
	rules: {
		'no-undef': 'off',
		'@typescript-eslint/no-unused-vars': [
			'error',
			{
				argsIgnorePattern: '^_',
				caughtErrorsIgnorePattern: '^_',
				varsIgnorePattern: '^_',
			},
		],
		'vue/multi-word-component-names': 'off',
	},
}
