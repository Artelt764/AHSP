import pdfplumber
import re
import pprint
import json
import os
import time


#======
def expand_pages(*specs):
    """Tiap spec: int (satu halaman) atau tuple (awal, akhir) untuk rentang inklusif."""
    pages = []
    for s in specs:
        if isinstance(s, tuple):
            pages.extend(range(s[0], s[1] + 1))
        else:
            pages.append(s)
    return sorted(set(pages))  # buang duplikat, urut naik

#=====
ahspPath = "Lampiran-IV-SE-DJBK-No-47-Tahun-2026-AHSP-Bidang-Sumber-Daya-Air.pdf"
outputJsonlPath = "AirahspTable.jsonl"
outputJsonPath = "AirahspTable.json"
historyPageNumsPath = "AirahspHistoryPageNumProcessed.json"


def main(pageNums,keepHistory):
    historyPageNums = load_progress(historyPageNumsPath)
    with pdfplumber.open(ahspPath) as pdf:
        for pageNum in pageNums:
            
            if keepHistory == True:
                if pageNum in historyPageNums:
                    print(f"halaman {pageNum} sudah ada di {historyPageNumsPath}, lewati")
                    continue
            if not keepHistory:
                remove_page_from_jsonl(pageNum)

            page = pdf.pages[pageNum-1] 
            tables = page.find_tables()
            prev_bottom = 0  # batas atas pencarian judul = ekor tabel sebelumnya (atau 0 di halaman)
            for table in tables:
                bboxTable = table.bbox
                title, titleNumbering = getTableTitle(page, bboxTable, prev_bottom)
                tableOutput = table.extract()
                tableParsed = parse_ahsp_table(tableOutput)

                if tableParsed["complete"] == False:
                    print(f"Tabel {titleNumbering}, Halaman {pageNum} tidak lengkap")

                tableReturn = {
                    "page_num":pageNum,
                    "title": title,
                    "title_numbering":titleNumbering,
                    "table_raw": tableOutput,
                    "table_parsed": tableParsed,
                    "complete": tableParsed['complete']
                }
                append_to_jsonl(tableReturn)
                prev_bottom = bboxTable[3]  # update batas bawah utk tabel berikutnya

            update_history(historyPageNumsPath, historyPageNums, [pageNum])
            print(f"halaman {pageNum} selesai diproses")
        

def getTableTitle(page, bboxTable, prev_bottom):
    pattern_start = re.compile(r'^\s*(\d+|[A-Z]+(?:\.(?:\d+|[A-Za-z]|\d+[a-zA-Z]+))+)\.?\s+')
    x0_table, top_table, x1_table, bottom_table = bboxTable

    crop_bbox = (0, max(0, prev_bottom), page.width, top_table)
    if crop_bbox[3] <= crop_bbox[1]:
        return None, None

    cropped = page.within_bbox(crop_bbox)
    lines = cropped.extract_text_lines()
    if not lines:
        return None, None

    title_lines = []
    titleNumbering = None
    for line in reversed(lines):
        text = line['text']
        title_lines.insert(0, text)
        m = pattern_start.match(text)
        if m:
            titleNumbering = m.group(1)   # misal "1.1.1.1"
            break

    if titleNumbering is None:
        return None, None

    title = ' '.join(t.strip() for t in title_lines)
    title = re.sub(r'\s+', ' ', title).strip()
    return title, titleNumbering


# =====================================

def parse_ahsp_table(raw_table):
    NO = re.compile(r'\d+\.?|[a-z]\.?')               # nomor urut: 1, 2., a, b
    COEF = re.compile(r'\d+(?:[.,]\d+)*')              # angka: 0,067 / 26,406
    KODE = re.compile(r'[A-Z]+(?:\.[A-Za-z0-9]+)+')    # kode: L.01, T.13.a, T.34
    GROUP_HURUF_ANGKA = re.compile(r'[A-Z]\.\d+\.?')   # nomor grup: B.1
    SECTION_RE = re.compile(r'^([ABC])\.(?:\s+.*)?$')  # "A. Tenaga Kerja" atau "A."
    ALL_NO = re.compile(r'\d+\.?|[a-z]\.?|[A-Z]\.\d+\.?')  # 1, 2., a, b, A.1, B.1.
    regexesOfGroupNumbering = [NO, GROUP_HURUF_ANGKA]  # variasi nomor pembuka grup

    result = {
        "tenaga_kerja": [], "bahan": [], "peralatan": [],
        "jumlah_harga_tenaga_kerja": None, "jumlah_harga_bahan": None,
        "jumlah_harga_alat": None, "total": None,
        "persen_laba": None, "nominal_laba": None,
        "harga_satuan_pekerjaan": None,
        "complete": True,
    }

    section_map = {'A': 'tenaga_kerja', 'B': 'bahan', 'C': 'peralatan'}
    current_section = None
    last_item = None
    group = None

    for row in raw_table[1:]:
        vals = [' '.join(c.split()) for c in row if c and c.strip()]
        if not vals:
            continue
        first = vals[0]

        # baris struktur
        if first.lower().startswith('jumlah'):
            last_item = group = None
            continue

        m = SECTION_RE.match(first)
        if m:
            current_section = section_map[m.group(1)]
            last_item = group = None
            continue
        if first in section_map:                      # format lama: "A" saja
            current_section = section_map[first]
            last_item = group = None
            continue

        if first.rstrip('.') == 'D':
            break
        if not current_section:
            continue

        has_coef = len(vals) >= 3 and COEF.fullmatch(vals[-1])

        # 1. baris data (berakhir dengan angka koefisien)
        if has_coef:
            satuan, koef = vals[-2], vals[-1]
            kode, body = None, vals[:-2]

            # kode dikenali dari bentuknya, berlaku untuk semua section (boleh kosong)
            if len(body) > 1 and KODE.fullmatch(body[-1]):
                kode, body = body[-1], body[:-1]

            # nomor urut di depan diambil jika formatnya 1, 2., a, b, A.1, B.1.
            no = None
            if len(body) > 1 and ALL_NO.fullmatch(body[0]):
                no, body = body[0], body[1:]

            uraian = ' '.join(body)  # uraian bisa pecah antar sel

            # item dianggap sejajar dengan grup saat numberingnya berformat 1, 2., B.1, A.2.
            if no:
                if no.rstrip('.').isdigit() or GROUP_HURUF_ANGKA.fullmatch(no):
                    group = None
                elif group:
                    uraian = f"{group} - {uraian}"

            koefisien = parse_koefisien(koef)
            if not isinstance(koefisien, float):
                result['complete'] = False

            last_item = {"uraian": uraian, "kode": kode, "satuan": satuan,
                         "koefisien": koefisien, "harga_satuan": '', "jumlah_harga": ''}
            result[current_section].append(last_item)
            continue

        # 2. judul kelompok: [nomor, teks], tanpa koefisien
        if len(vals) == 2:
            matched = False
            for regex in regexesOfGroupNumbering:
                if regex.fullmatch(vals[0]):
                    group = vals[1]
                    last_item = None
                    matched = True
                    break
            if matched:
                continue

        # 3. selain itu: dianggap lanjutan uraian baris sebelumnya
        if last_item is not None:
            last_item["uraian"] += ' ' + ' '.join(vals)
        else:
            result['complete'] = False
            print(f"BARIS TAK TERKLASIFIKASI: {vals}")

    if not (result["tenaga_kerja"] or result["bahan"] or result["peralatan"]):
        result['complete'] = False

    return result

def parse_koefisien(val):
    if not val or val.strip() == '':
        return None
    val = val.strip().replace('.', '').replace(',', '.')  # format ID: koma=desimal
    try:
        return float(val)
    except ValueError:
        return val  # biarin string kalau ternyata bukan angka murni (misal "....% x D")

def clean_uraian(text):
    if not text:
        return text
    return re.sub(r'\s+', ' ', text).strip()


#=================================================
#pindah ke js
def build_ahsp_table(parsed, koef_decimals=3):
    rows = []

    # header
    rows.append(['No', 'Uraian', 'Kode', 'Satuan', 'Koefisien', None,
                 'Harga Satuan (Rp)', 'Jumlah Harga (Rp)'])

    section_config = [
        ('A', 'Tenaga Kerja', 'tenaga_kerja', 'Jumlah Harga Tenaga Kerja', 'jumlah_harga_tenaga_kerja'),
        ('B', 'Bahan', 'bahan', 'Jumlah Harga Bahan', 'jumlah_harga_bahan'),
        ('C', 'Peralatan', 'peralatan', 'Jumlah Harga Alat', 'jumlah_harga_alat'),
    ]

    for kode_section, label_section, key_items, label_jumlah, key_jumlah in section_config:
        # baris section header, misal ['A', 'Tenaga Kerja', '', '', '', None, '', '']
        rows.append([kode_section, label_section, '', '', '', None, '', ''])

        # baris item di dalam section
        for item in parsed.get(key_items, []):
            rows.append([
                '',
                item.get('uraian', ''),
                item.get('kode') or '',
                item.get('satuan') or '',
                format_koefisien(item.get('koefisien'), koef_decimals),
                None,
                item.get('harga_satuan') or '',
                item.get('jumlah_harga') or '',
            ])

        # baris "Jumlah Harga ..."
        rows.append([label_jumlah, None, None, None, None, None, None,
                     parsed.get(key_jumlah) or ''])

    # baris D
    rows.append(['D', 'Jumlah Harga Tenaga Kerja, Bahan dan Peralatan (A+B+C)',
                 None, None, None, None, None, parsed.get('total') or ''])

    # baris E
    rows.append(['E', 'Biaya Umum dan Keuntungan (10% - 15%) x D',
                 None, None, None, f"{parsed.get('persen_laba') or '...'}% x D",
                 None, parsed.get('nominal_laba') or ''])

    # baris F
    rows.append(['F', 'Harga Satuan Pekerjaan (D+E)',
                 None, None, None, None, None,
                 parsed.get('harga_satuan_pekerjaan') or ''])

    return rows

def format_koefisien(val, decimals=3):
    """Ubah float balik ke format string Indonesia (titik ribuan, koma desimal)."""
    if val is None:
        return ''
    if isinstance(val, str):
        return val  # sudah string (misal '....% x D'), biarin apa adanya
    # float -> string dengan koma sebagai desimal
    formatted = f'{val:.{decimals}f}'
    # buang trailing zero berlebihan kalau perlu, atau biarkan tetap decimals digit
    return formatted.replace('.', ',')

#==============================
def append_to_jsonl(tableReturn):
    with open(outputJsonlPath, 'a', encoding='utf-8') as f:
        f.write(json.dumps(tableReturn, ensure_ascii=False) + '\n')

def load_progress (historyPageNumsPath):
    if not os.path.exists(historyPageNumsPath):
        return set()
    with open(historyPageNumsPath,'r',encoding='utf-8') as f:
        historyPageNum = set(json.load(f))
        return historyPageNum

def update_history(historyPageNumsPath,historyPageNums,pageNums):
    historyPageNums.update(pageNums)
    historyPageNumsSetted = sorted(historyPageNums)
    with open (historyPageNumsPath,'w',encoding='utf-8') as f:
        json.dump(historyPageNumsSetted,f)

def remove_page_from_jsonl(pageNum):
    if not os.path.exists(outputJsonlPath):
        return
    tmpPath = outputJsonlPath + ".tmp"
    with open(outputJsonlPath, 'r', encoding='utf-8') as fin, \
         open(tmpPath, 'w', encoding='utf-8') as fout:
        for line in fin:
            if line.strip() and json.loads(line)["page_num"] != pageNum:
                fout.write(line)
    os.replace(tmpPath, outputJsonlPath)

def jsonl_to_json(jsonlPath, jsonPath):
    with open(jsonlPath, 'r', encoding='utf-8') as fin:
        records = [json.loads(line) for line in fin if line.strip()]

    # Hapus table_raw dari setiap record sebelum dump
    for record in records:
        record.pop('table_raw', None)

    records.sort(key=lambda r: numbering_key(r.get("title_numbering")))
    with open(jsonPath, 'w', encoding='utf-8') as fout:
        json.dump(records, fout, ensure_ascii=False)

def numbering_key(numbering):
    if not numbering:
        return ((2, 0, ''),)          # tanpa nomor: taruh di akhir
    key = []
    for part in numbering.split('.'):
        if part.isdigit():
            key.append((0, int(part), ''))
        else:
            key.append((1, 0, part.lower()))
    return tuple(key)
#========================

t = time.time()
pageNums = expand_pages((878,881))
main(pageNums,False)
jsonl_to_json(outputJsonlPath,outputJsonPath)
print((time.time() - t), "waktu olah")
# pprint.pprint(tabelCek, sort_dicts=False)

