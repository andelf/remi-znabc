local UserDictionary = {}
UserDictionary.__index = UserDictionary
local opened = {}

function UserDictionary.key(codes)
  return table.concat(codes, ",")
end

local function decode(key, value)
  local stage, uses, touched = value:match("^(%a+)\t(%d+)\t(%d+)$")
  if not stage or not ({temporary = true, common = true, history = true, deleted = true})[stage] then
    return nil
  end
  local codes = {}
  for code in key:gmatch("%d+") do
    codes[#codes + 1] = tonumber(code)
  end
  if #codes < 2 or #codes > 9 or UserDictionary.key(codes) ~= key then
    return nil
  end
  return {codes = codes, stage = stage, uses = tonumber(uses), touched = tonumber(touched)}
end

function UserDictionary.new(database, options)
  options = options or {}
  local self = setmetatable({database = database, entries = {}, words = {},
    promotion_uses = math.max(1, options.promotion_uses or 3),
    temporary_capacity = math.max(1, options.temporary_capacity or 2000),
    clock = options.clock or os.time}, UserDictionary)
  for key, value in database:query("word/"):iter() do
    local record = decode(key:sub(6), value)
    if record then
      self.entries[UserDictionary.key(record.codes)] = record
      if record.stage == "temporary" or record.stage == "common" then
        self.words[#record.codes] = self.words[#record.codes] or {}
        self.words[#record.codes][UserDictionary.key(record.codes)] = record
      end
    end
  end
  return self
end

function UserDictionary.acquire(name, options)
  if opened[name] then
    opened[name].references = opened[name].references + 1
    return opened[name]
  end
  local database = LevelDb(name)
  assert(database and database:open(), "无法打开智能 ABC 用户词库：" .. name)
  local self = UserDictionary.new(database, options)
  self.name, self.references = name, 1
  opened[name] = self
  return self
end

function UserDictionary:release()
  self.references = self.references - 1
  if self.references == 0 then
    self.database:close()
    opened[self.name] = nil
  end
end

function UserDictionary:write(record)
  local key = UserDictionary.key(record.codes)
  local value = table.concat({record.stage, record.uses, record.touched}, "\t")
  if not self.database:update("word/" .. key, value) then
    return false, "用户词库写入失败"
  end
  self.entries[key] = record
  self.words[#record.codes] = self.words[#record.codes] or {}
  self.words[#record.codes][key] =
    (record.stage == "temporary" or record.stage == "common") and record or nil
  return true
end

function UserDictionary:remember(codes, base)
  local key = UserDictionary.key(codes)
  local previous = self.entries[key]
  if previous and previous.stage == "deleted" then
    return true
  end
  if #codes < 2 or #codes > 9 then
    return true
  end
  local record = {codes = {table.unpack(codes)}, touched = self.clock(),
    stage = previous and previous.stage or (base and "history" or "temporary"),
    uses = previous and previous.uses + 1 or (base and 1 or 0)}
  if record.stage == "temporary" and record.uses >= self.promotion_uses then
    record.stage = "common"
  end
  local evictions = {}
  if not previous and not base then
    local temporary = {}
    for entry_key, entry in pairs(self.entries) do
      if entry.stage == "temporary" then
        temporary[#temporary + 1] = {key = entry_key, record = entry}
      end
    end
    table.sort(temporary, function(left, right)
      if left.record.uses ~= right.record.uses then
        return left.record.uses < right.record.uses
      end
      if left.record.touched ~= right.record.touched then
        return left.record.touched < right.record.touched
      end
      return left.key < right.key
    end)
    for index = 1, #temporary - self.temporary_capacity + 1 do
      evictions[#evictions + 1] = temporary[index].key
    end
  end
  local saved, message = self:write(record)
  if not saved then
    return false, message
  end
  for _, evict in ipairs(evictions) do
    if not self.database:erase("word/" .. evict) then
      return false, "临时词淘汰失败"
    end
    self.words[#self.entries[evict].codes][evict] = nil
    self.entries[evict] = nil
  end
  return true
end

function UserDictionary:remove(codes)
  return self:write({codes = {table.unpack(codes)}, stage = "deleted", uses = 0, touched = self.clock()})
end

function UserDictionary:get(codes)
  local record = self.entries[UserDictionary.key(codes)]
  return record and record.stage ~= "deleted" and record or nil
end

return UserDictionary
