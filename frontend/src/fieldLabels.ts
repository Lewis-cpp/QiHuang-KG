// spec §5.6: per-type field order and Chinese labels. Keys come from attributes_json in the current batch.
// A configured `X_zh` field shows its `X_en` sibling underneath; unlisted keys go to "其他属性".

export const fieldLabels: Record<string, [string, string][]> = {
  formula: [
    ['name_pinyin', '拼音'], ['name_en', '英文名'], ['subcategory', '子分类'], ['source_text_key', '出处'],
    ['source_chapter', '出处篇章'], ['treatment_principle', '治法'], ['preparation_zh', '制法'],
    ['modifications', '加减'], ['rhyme', '方歌'], ['description_zh', '说明'],
  ],
  herb: [
    ['name_pinyin', '拼音'], ['name_latin', '拉丁名'], ['name_en', '英文名'], ['nature', '性'], ['flavors', '味'],
    ['actions', '功效'], ['indications', '主治'], ['dosage_range', '用量范围'], ['processing_methods', '炮制'],
    ['classical_references', '古籍记载'], ['pharmacology', '药理'], ['description_zh', '说明'],
  ],
  pattern: [
    ['name_pinyin', '拼音'], ['name_en', '英文名'], ['cardinal_symptoms', '主症'], ['secondary_symptoms', '次症'],
    ['tongue', '舌象'], ['pulse', '脉象'], ['etiology_zh', '病因'], ['pathomechanism_zh', '病机'],
    ['treatment_principle', '治法'], ['organ_systems', '相关脏腑'], ['description_zh', '说明'],
  ],
  text: [
    ['title_pinyin', '拼音'], ['title_en', '英文名'], ['author', '作者'], ['dynasty_zh', '朝代'],
    ['approximate_date', '成书年代'], ['tradition', '学派'], ['significance', '学术地位'], ['description_zh', '说明'],
  ],
  patent_medicine: [['Pinyin_term', '拼音'], ['Routes_of_administration', '给药途径']],
  herbal_piece: [['Chinese_synonyms', '中文异名'], ['Pinyin_term', '拼音'], ['English_term', '英文名'], ['Sources', '来源']],
  tcm_term: [
    ['Chinese_group', '中文分组'], ['English_group', '英文分组'], ['Pinyin_term', '拼音'],
    ['Chinese_synonyms', '中文同义词'], ['English_term', '英文名'], ['Synonyms', '英文同义词'],
    ['English_definition_description', '英文定义'],
  ],
  icd11_code: [['code', '编码']],
  medicinal_property: [['class', '类别'], ['name', '名称']],
}

// Long fields shown in a collapsed block instead of inline.
export const collapsedFields: Record<string, string[]> = { text: ['passages'] }

// spec §5.0 item 5: source safety text, shown in its own section with a fixed notice.
export const safetyFields: [string, string][] = [
  ['contraindications_zh', '禁忌'], ['safety_notes_zh', '安全提示'], ['pregnancy', '孕期'],
  ['lactation', '哺乳期'], ['pediatric', '儿童'], ['acute_use_note', '急症使用说明'],
]

// Shown elsewhere on the page (the header), so never repeated as attributes.
export const hiddenFields = ['category']

export const valueLabels: Record<string, Record<string, string>> = {
  nature: {
    very_cold: '大寒', cold: '寒', slightly_cold: '微寒', cool: '凉', neutral: '平',
    slightly_warm: '微温', warm: '温', hot: '热',
  },
  flavors: {
    sour: '酸', bitter: '苦', slightly_bitter: '微苦', sweet: '甘', slightly_sweet: '微甘', acrid: '辛',
    pungent: '辛', salty: '咸', bland: '淡', astringent: '涩',
  },
  organ_systems: {
    heart: '心', liver: '肝', spleen: '脾', lung: '肺', kidney: '肾', pericardium: '心包', gallbladder: '胆',
    stomach: '胃', small_intestine: '小肠', large_intestine: '大肠', bladder: '膀胱',
  },
}

// Routes keep the source value next to the translation (spec §5.6).
export const routeNames: Record<string, string> = { Oral: '口服', Topical: '外用', Injection: '注射' }

// Labels for keys inside nested source objects; unknown keys are shown as-is.
export const subKeyLabels: Record<string, string> = {
  min: '最小', max: '最大', unit: '单位', notes: '说明', note: '说明', add: '加', remove: '减',
  condition: '症状', rationale: '理由', classification: '品级', passage: '原文', text_key: '古籍',
  body: '舌质', coating: '舌苔', type: '类型', pinyin: '拼音', summary: '概述', evidence_notes: '依据',
  source: '来源', source_key: '来源', chapter: '篇章', title: '标题', text: '原文', annotations: '注释',
  phrase: '词句', target: '对象', is_primary: '主要', method: '方法', purpose: '目的', category: '分类',
  name: '名称', class: '类别', effect: '作用', indication: '适应证', evidence_level: '证据等级',
  active_constituents: '主要成分', modern_clinical_uses: '现代临床应用',
}
