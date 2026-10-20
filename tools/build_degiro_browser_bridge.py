"""Build the installable userscript from the same parser Bob uses. No dependencies."""
from pathlib import Path
BASE = Path(__file__).resolve().parents[1]
META = '''// ==UserScript==
// @name         Bob DEGIRO Export-Brücke
// @namespace    https://bob-private-scanner.onrender.com/
// @version      1.2.0
// @description  Übergibt ausgewählte DEGIRO-Portfolioexporte an Bob. Keine Anmeldung oder Orders.
// @match        https://trader.degiro.nl/*
// @match        https://bob-private-scanner.onrender.com/*
// @grant        unsafeWindow
// @grant        GM_getValue
// @grant        GM_setValue
// @grant        GM_deleteValue
// @grant        GM_addValueChangeListener
// @run-at       document-start
// @inject-into  page
// @noframes
// @license      MIT
// ==/UserScript==
'''

def build():
    text = (BASE / 'degiro_report_import.js').read_text()
    parser = text[text.index('function parseRows('):text.index('function node(')]
    runtime = (BASE / 'browser_bridge/runtime.js').read_text()
    return META + '\n(function(){\n\"use strict\";\n' + parser + '\n' + runtime + '\n})();\n'

if __name__ == '__main__':
    (BASE / 'bob_degiro_export.user.js').write_text(build())
