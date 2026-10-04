from ekstrakAHSP import append_to_jsonl,load_progress,update_history,remove_page_from_jsonl,jsonl_to_json

table_return_template = {
    "page_num":None,
    "title": None,
    "title_numbering":None,
    "table_raw": None,
    "table_parsed": None,
    "complete": True
}

ahsp_table_parsed_template = {
    "tenaga_kerja": [], "bahan": [], "peralatan": [],
    "jumlah_harga_tenaga_kerja": None, "jumlah_harga_bahan": None,
    "jumlah_harga_alat": None, "total": None,
    "persen_laba": None, "nominal_laba": None,
    "harga_satuan_pekerjaan": None,
    "complete": True,
}

itemDictTemplate = {"uraian":None, "kode": None, "satuan": None,
    "koefisien":None, "harga_satuan": '', "jumlah_harga": ''}

jsonlPath = "JalanahspTable.jsonl"
jsonPath = "JalanahspTable.json"
historyPath = "JalanahspHistoryPageNumProcessed.json"

def manualPush(arrOfAhsp):
    historypageNums = load_progress(historyPath)

    for ahsp in arrOfAhsp:
        pageNum = ahsp["page_num"]
        if pageNum in historypageNums:
            remove_page_from_jsonl(pageNum,jsonlPath)

    for ahsp in arrOfAhsp:    
        append_to_jsonl(ahsp,jsonlPath)
        print(ahsp["title"])
        pageNum = ahsp["page_num"]
        update_history(historyPath,historypageNums,[pageNum])
    jsonl_to_json(jsonlPath,jsonPath)
        


def createAhsp (page, title_numbering, title, arrOfDictTenagaKerja, arrofDictBahan, arrOfDictAlat):

    a = table_return_template.copy()
    b=ahsp_table_parsed_template.copy()
    
    b["tenaga_kerja"] = arrOfDictTenagaKerja
    b["bahan"] = arrofDictBahan
    b["peralatan"] = arrOfDictAlat

    a["table_parsed"] = b
    a["page_num"] = page
    a["title"] = title
    a["title_numbering"] = title_numbering
    return a


def resource(uraian,kode,satuan,koefisien):
    a = itemDictTemplate.copy()
    a["uraian"] = uraian
    a["kode"] = kode
    a["satuan"] = satuan
    a["koefisien"] = koefisien
    return a

arrayToPush = [
    createAhsp(
        350, "C.14", "C.14 Timbunan Biasa dari Sumber Galian (3.2.(1a))",
        [
            resource("Pekerja","L01","Jam",0.0306),
            resource("Mandor","L03","Jam",0.0076),
        ],
        [
            resource("Bahan Timbunan Biasa (Tanah Urug)","M08","m3",1.165)
        ],
        [
            resource("Excavator","E10","Jam",0.0126),
            resource("DUMP TRUCK TRONTON 10 TON", "E35", "Jam", 0.2670),
            resource("Motor Grader", "E13", "Jam", 0.0076),
            resource("Sheepfoot Roller" ,"E16a" ,"Jam", 0.0095),
            resource("Tandem Roller", "E17", "Jam", 0.0052),
            resource("Water tank truck", "E23", "Jam", 0.0070),
            resource("Alat Bantu","","Ls",1)
        ]
    )

]


if __name__ == "__main__":
    manualPush(arrayToPush)
