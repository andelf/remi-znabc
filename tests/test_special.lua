local project = arg[1] or "."
package.path = project .. "/rime/lua/?.lua;" .. package.path
local special = require("znabc.special").new(project .. "/rime/znabc_data")
local examples = {
  i = "一", I = "壹", i1 = "一", I1 = "壹", i123 = "一二三", I123 = "壹贰叁",
  i0 = "○", I0 = "零", i2006n6y3sr = "二○○六年六月三十日", iqk = "千克",
  ["i+"] = "加", ["i$"] = "元", i1b2s3 = "一百二十三", I1b2s3 = "壹佰贰拾叁",
  i2w = "二万", ix = "升", ia = "秒", iz = "兆", ["i1/2"] = "一除二",
  ["i-3"] = "减三", ["i2*3"] = "二乘三", iNSBQ = "年十百千",
}
for input, expected in pairs(examples) do
  assert(special:quantity_text(input) == expected, input)
end
for _, input in ipairs({"", "l1", "i12.5", "i!", "i" .. string.rep("1", 20)}) do
  assert(special:quantity_text(input) == nil, input)
end
assert(special:quantity_text("i" .. string.rep("1", 19)))
local counts = {94, 72, 94, 83, 86, 48, 66, 63, 76}
for zone, count in ipairs(counts) do
  local rows = special:symbol_candidates(tostring(zone))
  assert(#rows == count, tostring(zone))
  assert(rows[1].source == "symbol")
end
assert(special:symbol_candidates("1")[1].text == "　")
assert(special:symbol_candidates("3")[1].text == "！")
assert(#special:symbol_candidates("0") == 0)
local function includes(input, character)
  local seen, found = {}, false
  for _, row in ipairs(special:gbk_candidates(input)) do
    assert(not seen[row.text], "duplicate " .. input)
    seen[row.text] = true
    if row.text == character then found = true end
  end
  return found
end
for _, input in ipairs({"rong34", "rong3414", "r34144", "ro34"}) do
  assert(includes(input, "鎔"), input)
end
assert(includes("pan335734", "槃"))
assert(includes("cu4", "麤"))
assert(includes("aes", "厑"))
assert(includes("hang", "行") and includes("xing", "行"))
for _, input in ipairs({"", "nihao", "rong9", "rong3414444", "1234567", "i1", "rong["}) do
  assert(#special:gbk_candidates(input) == 0, input)
end
assert(not includes("rong111", "鎔"))
print("special mode checks passed")
