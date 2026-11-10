local parser = require("znabc.parser")
local Dictionary = require("znabc.dictionary")
local Special = require("znabc.special")
local Engine = {}
Engine.__index = Engine

local function matches(character, unit)
  if not character then
    return false
  end
  if unit.abbreviated then
    local high = math.floor(character.packed / 256)
    if high ~= unit.initial and parser.initial_letter(high):upper():byte() ~= unit.initial then
      return false
    end
  elseif character.packed ~= unit.packed then
    return false
  end
  return unit.shape == 0 or unit.shape == character.shape or unit.shape == math.floor(character.shape / 16) * 16
end

function Engine.new(root, user_dictionary, include_supplement)
  local affixes = {}
  local file = assert(io.open(root .. "/affixes.tsv", "rb"))
  for line in file:lines() do
    local direction, encoded = line:match("^(%d+)\t([%d,]+)")
    local codes = {}
    for code in encoded:gmatch("%d+") do codes[#codes + 1] = tonumber(code) end
    affixes[#affixes + 1] = {direction = tonumber(direction), codes = codes}
  end
  file:close()
  return setmetatable({dictionary = Dictionary.new(root, include_supplement), special = Special.new(root), affixes = affixes,
    user_dictionary = user_dictionary, user_enabled = true}, Engine)
end

function Engine:affix_index(candidates, consumed, units, mode, input_length, start, single_character)
  if single_character or (mode ~= "character" and mode ~= "phrase") then return nil end
  local width = 0
  for _, unit in ipairs(units) do
    if unit.finish <= consumed then width = width + 1 end
  end
  local direction
  if start > 0 and consumed == input_length and width <= 2 then
    direction = 2
  elseif start == 0 and width == 1 and consumed < input_length then
    direction = 1
  else
    return nil
  end
  for _, affix in ipairs(self.affixes) do
    if #affix.codes == width and (affix.direction == direction or affix.direction == 3) then
      local matched = true
      for index, code in ipairs(affix.codes) do
        if not matches(self.dictionary.characters[code], units[index]) then matched = false; break end
      end
      if matched then
        local identity = table.concat(affix.codes, ",")
        for index, candidate in ipairs(candidates) do
          local codes = candidate.codes or (candidate.code and {candidate.code})
          if codes and table.concat(codes, ",") == identity and
              (candidate.consumed or consumed) == consumed then return index - 1 end
        end
        return nil
      end
    end
  end
end

function Engine:has_base(codes)
  local first, second = self.dictionary.characters[codes[1]], self.dictionary.characters[codes[2]]
  if not first or not second then
    return false
  end
  local key = parser.initial_letter(math.floor(first.packed / 256)) ..
    parser.initial_letter(math.floor(second.packed / 256))
  local identity = table.concat(codes, ",")
  for _, phrase in ipairs(self.dictionary:phrase_bucket(key)[#codes] or {}) do
    if table.concat(phrase.codes, ",") == identity then
      return true
    end
  end
  return false
end

function Engine:user_candidates(units, width)
  local result = {}
  if not self.user_dictionary or not self.user_enabled then
    return result
  end
  for _, record in pairs(self.user_dictionary.words[width] or {}) do
    local text, matched = {}, true
    for index, code in ipairs(record.codes) do
      local character = self.dictionary.characters[code]
      if not matches(character, units[index]) then
        matched = false
        break
      end
      text[#text + 1] = character.text
    end
    if matched then
      result[#result + 1] = {text = table.concat(text), codes = record.codes,
        weight = 0, order = 0, source = "user"}
    end
  end
  return result
end

function Engine:learning_rank(item)
  local record = self.user_enabled and self.user_dictionary and self.user_dictionary:get(item.codes)
  if not record then
    return 0, 0, 0
  end
  local ranks = {temporary = 1, history = 2, common = 3}
  return ranks[record.stage] or 0, record.uses, record.touched
end

function Engine:word_character(input, suffix)
  local phrases, consumed, units, mode = self:query(input)
  if mode ~= "phrase" or consumed ~= #input then
    return {}, 0, units, "invalid"
  end
  local result, seen = {}, {}
  for _, phrase in ipairs(phrases) do
    local code = suffix == "[" and phrase.codes[1] or phrase.codes[#phrase.codes]
    local character = self.dictionary.characters[code]
    if character and not seen[character.text] then
      result[#result + 1] = {text = character.text, code = code, word = phrase.text,
        weight = phrase.weight, order = phrase.order, source = "word_character"}
      seen[character.text] = true
    end
  end
  return result, #input + 1, units, "word_character"
end

function Engine:query(input, single_character)
  local zone = input:match("^v([1-9])$")
  if zone then
    return self.special:symbol_candidates(zone), #input, {}, "symbol"
  end
  local base, suffix = input:match("^(.-)([%[%]])$")
  if suffix and not base:find("[%[%]]") then
    return self:word_character(base, suffix)
  end
  if input:find("[%[%]]") then
    return {}, 0, {}, "invalid"
  end
  if input:match("^[1-8]+$") then
    return self.dictionary:shape_bucket(input:sub(1, 1))[input] or {}, #input, {}, "shape"
  end
  local units = parser.parse(input)
  if #units == 0 then
    return {}, 0, units, "invalid"
  end
  if #units > 1 and not single_character then
    local key = parser.initial_letter(units[1].initial) .. parser.initial_letter(units[2].initial)
    local bucket = self.dictionary:phrase_bucket(key)
    for width = math.min(#units, 9), 2, -1 do
      local candidates = self:user_candidates(units, width)
      local seen = {}
      for _, candidate in ipairs(candidates) do
        seen[table.concat(candidate.codes, ",")] = true
      end
      for _, phrase in ipairs(bucket[width] or {}) do
        local matched = true
        for index, code in ipairs(phrase.codes) do
          if not matches(self.dictionary.characters[code], units[index]) then
            matched = false
            break
          end
        end
        if matched and not seen[table.concat(phrase.codes, ",")] then
          candidates[#candidates + 1] = phrase
          if #candidates * width * 2 >= 1020 then
            break
          end
        end
      end
      if #candidates > 0 then
        table.sort(candidates, function(left, right)
          local left_rank, left_uses, left_time = self:learning_rank(left)
          local right_rank, right_uses, right_time = self:learning_rank(right)
          if left_rank ~= right_rank then
            return left_rank > right_rank
          end
          if left_uses ~= right_uses then
            return left_uses > right_uses
          end
          if left_time ~= right_time then
            return left_time > right_time
          end
          if left.weight ~= right.weight then
            return left.weight > right.weight
          end
          if left.order ~= right.order then
            return left.order < right.order
          end
          return table.concat(left.codes, ",") < table.concat(right.codes, ",")
        end)
        return candidates, units[width].finish, units, "phrase"
      end
    end
  end
  local unit = units[1]
  local candidates = {}
  local initial = parser.initial_letter(unit.initial)
  local frequent_only = unit.abbreviated and unit.shape == 0 and initial ~= "a" and initial ~= "o" and initial ~= "e"
  if unit.abbreviated and unit.shape == 0 and not frequent_only then
    unit = {packed = unit.packed, initial = unit.initial, shape = 0, abbreviated = false, finish = unit.finish}
  end
  for _, character in ipairs(self.dictionary.initials[initial] or {}) do
    if matches(character, unit) and (not frequent_only or
        (character.source ~= "supplement" and character.weight > 204) or
        (character.source == "supplement" and character.packed == unit.packed)) then
      candidates[#candidates + 1] = character
    end
  end
  table.sort(candidates, function(left, right)
    if (left.source == "supplement") ~= (right.source == "supplement") then
      return left.source ~= "supplement"
    end
    if left.weight ~= right.weight then
      return left.weight > right.weight
    end
    return left.code < right.code
  end)
  return candidates, unit.finish, units, "character"
end

function Engine:query_gbk(input)
  return self.special:gbk_candidates(input), #input, {}, "gbk"
end

function Engine:query_menu(input, single_character)
  local candidates, consumed, units, mode = self:query(input, single_character)
  if mode ~= "phrase" then
    return candidates, consumed, units, mode
  end
  local result = {}
  for _, candidate in ipairs(candidates) do
    result[#result + 1] = candidate
  end
  local characters, character_consumed = self:query(input, true)
  for _, character in ipairs(characters) do
    local candidate = {}
    for key, value in pairs(character) do
      candidate[key] = value
    end
    candidate.consumed = character_consumed
    result[#result + 1] = candidate
  end
  return result, consumed, units, mode
end

return Engine

