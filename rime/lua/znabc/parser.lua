local parser = {}

local tokens = {
  "ZH", "SH", "CH", "ING", "AI", "AN", "ANG", "AO", "EI", "EN",
  "ENG", "IA", "IAN", "IANG", "IAO", "IE", "IN", "IU", "ONG", "OU",
  "UA", "UAI", "UAN", "UE", "UN", "UENG", "UI", "UO", "UANG", "ER", "IONG",
}

local packed_tokens = {}
for index, token in ipairs(tokens) do
  packed_tokens[token .. string.rep("0", 4 - #token)] = index
end

local function vowel(character)
  return character ~= "" and ("AEIOUV"):find(character, 1, true) ~= nil
end

local function letter(character)
  return character ~= "" and character >= "A" and character <= "Z"
end

local function number(character)
  return character ~= "" and character >= "0" and character <= "9"
end

local function token_value(buffer)
  return packed_tokens[table.concat(buffer)]
end

local function parse_one(input, start)
  local position = start
  local first = input:sub(position, position)
  if not letter(first) or first == "I" or first == "U" or first == "V" then
    return nil
  end
  local initial = first:byte()
  local high, low = 0, 0
  local buffer = {"0", "0", "0", "0"}
  if not vowel(first) then
    high = first:byte()
    position = position + 1
    if (first == "Z" or first == "S" or first == "C") and input:sub(position, position) == "H" then
      high = ({Z = 1, S = 2, C = 3})[first]
      initial = high
      position = position + 1
    end
  end
  local next_character = input:sub(position, position)
  if vowel(next_character) then
    low = next_character:byte()
    buffer[1] = next_character
    position = position + 1
    for index = 2, 4 do
      local character = input:sub(position, position)
      if character == "" or number(character) then
        break
      end
      buffer[index] = character
      position = position + 1
    end
    for index = 4, 2, -1 do
      local value = token_value(buffer)
      if value then
        low = value
        break
      end
      if buffer[index] ~= "0" then
        buffer[index] = "0"
        position = position - 1
      end
    end
    next_character = input:sub(position, position)
    local previous = input:sub(position - 1, position - 1)
    if vowel(next_character) and (previous == "N" or previous == "G" or previous == "R") then
      position = position - 1
      for index = 4, 2, -1 do
        if buffer[index] ~= "0" then
          buffer[index] = "0"
          break
        end
      end
      low = 0
      for index = 4, 2, -1 do
        local value = token_value(buffer)
        if value then
          low = value
          break
        end
        if buffer[index] ~= "0" then
          buffer[index] = "0"
          position = position - 1
        end
      end
      if low == 0 then
        low = buffer[1]:byte()
      end
    end
  end
  if high == 0 then
    high, low = low, 0
  end
  if low == 86 and (initial == 74 or initial == 81 or initial == 88) then
    low = 85
  end
  local shape = 0
  local count = 0
  while position <= #input do
    local character = input:sub(position, position)
    if letter(character) then
      break
    end
    position = position + 1
    if character == "'" then
      break
    end
    if count < 6 and character >= "1" and character <= "8" then
      if count == 0 then
        shape = tonumber(character) * 16
      elseif count == 1 then
        shape = shape + tonumber(character)
      end
    end
    count = count + 1
    if count == 6 then
      while position <= #input do
        local trailing = input:sub(position, position)
        position = position + 1
        if letter(trailing) then
          break
        end
      end
      break
    end
  end
  local abbreviated = low == 0 and initial == high
  local flags = abbreviated and 4 or 2
  if shape ~= 0 then
    flags = flags + 8
  end
  return {
    start = start - 1,
    finish = position - 1,
    packed = high * 256 + low,
    initial = initial,
    shape = shape,
    abbreviated = abbreviated,
    flags = flags,
  }
end

function parser.parse(raw)
  local input = raw:upper()
  local units = {}
  local position = 1
  while position <= #input and #units < 10 do
    local unit = parse_one(input, position)
    if not unit or unit.finish < position then
      break
    end
    units[#units + 1] = unit
    position = unit.finish + 1
  end
  return units, position - 1
end

function parser.initial_letter(value)
  if value > 0 and value <= #tokens then
    return tokens[value]:sub(1, 1):lower()
  end
  return string.char(value):lower()
end

function parser.syllable(packed)
  local result = {}
  for _, value in ipairs({math.floor(packed / 256), packed % 256}) do
    if value ~= 0 then
      result[#result + 1] = tokens[value] or string.char(value)
    end
  end
  return table.concat(result):lower()
end

return parser

