local parser = require("znabc.parser")
local Dictionary = require("znabc.dictionary")
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

function Engine.new(root)
  return setmetatable({dictionary = Dictionary.new(root)}, Engine)
end

function Engine:query(input)
  if input:match("^[1-8]+$") then
    return self.dictionary:shape_bucket(input:sub(1, 1))[input] or {}, #input, {}, "shape"
  end
  local units = parser.parse(input)
  if #units == 0 then
    return {}, 0, units, "invalid"
  end
  if #units > 1 then
    local key = parser.initial_letter(units[1].initial) .. parser.initial_letter(units[2].initial)
    local bucket = self.dictionary:phrase_bucket(key)
    for width = math.min(#units, 9), 2, -1 do
      local candidates = {}
      for _, phrase in ipairs(bucket[width] or {}) do
        local matched = true
        for index, code in ipairs(phrase.codes) do
          if not matches(self.dictionary.characters[code], units[index]) then
            matched = false
            break
          end
        end
        if matched then
          candidates[#candidates + 1] = phrase
          if #candidates * width * 2 >= 1020 then
            break
          end
        end
      end
      if #candidates > 0 then
        table.sort(candidates, function(left, right)
          if left.weight ~= right.weight then
            return left.weight > right.weight
          end
          return left.order < right.order
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
    if matches(character, unit) and (not frequent_only or character.weight > 204) then
      candidates[#candidates + 1] = character
    end
  end
  table.sort(candidates, function(left, right)
    if left.weight ~= right.weight then
      return left.weight > right.weight
    end
    return left.code < right.code
  end)
  return candidates, unit.finish, units, "character"
end

return Engine

