local Learning = {}
Learning.__index = Learning

function Learning.new(engine, store, options)
  return setmetatable({engine = engine, store = store, records = {},
    min_length = math.max(2, options.min_length or 2),
    max_length = math.min(9, options.max_length or 9)}, Learning)
end

function Learning:record(input, segment, candidates, consumed, mode)
  self.records[segment.start] = {input = input, candidates = candidates, consumed = consumed, mode = mode}
end

function Learning:selected(context, segment)
  local candidate = segment:get_selected_candidate()
  local record = self.records[segment.start]
  if not candidate or candidate.type ~= "znabc" or not record or
      record.mode == "shape" or record.mode == "word_character" or record.mode == "symbol" or record.mode == "gbk" then
    return nil
  end
  local item = record.candidates[segment.selected_index + 1]
  local consumed = item and (item.consumed or record.consumed)
  if not item or item.text ~= candidate.text or candidate._end ~= segment.start + consumed or
      context.input:sub(segment.start + 1, candidate._end) ~= record.input:sub(1, consumed) then
    return nil
  end
  return item.codes or (item.code and {item.code})
end

function Learning:commit(context)
  if not self.store or not context:get_option("znabc_learning") or
      not context:get_option("znabc_user_dict") or context:get_option("ascii_mode") then
    return true
  end
  local all_codes, selected = {}, {}
  local finish = 0
  for _, segment in ipairs(context.composition:toSegmentation():get_segments()) do
    if segment._end > segment.start then
      if segment.start ~= finish or (segment.status ~= "kSelected" and segment.status ~= "kConfirmed") then
        return true
      end
      local codes = self:selected(context, segment)
      if not codes then
        return true
      end
      selected[#selected + 1] = codes
      for _, code in ipairs(codes) do
        all_codes[#all_codes + 1] = code
      end
      finish = segment._end
    end
  end
  if finish ~= #context.input then
    return true
  end
  local saved = {}
  selected[#selected + 1] = all_codes
  for _, codes in ipairs(selected) do
    local key = table.concat(codes, ",")
    if #codes >= self.min_length and #codes <= self.max_length and not saved[key] then
      local ok, message = self.store:remember(codes, self.engine:has_base(codes))
      if not ok then
        return false, message
      end
      saved[key] = true
    end
  end
  return true
end

function Learning:remove(context)
  if not self.store or not context:get_option("znabc_user_dict") then
    return true
  end
  local codes = self:selected(context, context.composition:back())
  if codes and #codes >= 2 then
    return self.store:remove(codes)
  end
  return true
end

return Learning
