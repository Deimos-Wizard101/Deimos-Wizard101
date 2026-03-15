from .quest_data import QuestData
from wizwalker.memory.memory_object import MemoryObject, DynamicMemoryObject


# 48 8B ? ? ? ? ? 48 8B 97 ? ? ? ? 48 8B ? E8 ? ? ? ? 33 D2

# WizardGraphicalClient.exe+AD7D77 - 48 8B 1D 62059102     - mov rbx,[WizardGraphicalClient.exe+33E82E0]
# WizardGraphicalClient.exe+AD7D7E - 48 8B 97 90040000     - mov rdx,[rdi+00000490]
# WizardGraphicalClient.exe+AD7D85 - 48 8B CB              - mov rcx,rbx
# WizardGraphicalClient.exe+AD7D88 - E8 83C14E00           - call WizardGraphicalClient.exe+FC3F10
# WizardGraphicalClient.exe+AD7D8D - 33 D2                 - xor edx,edx
# WizardGraphicalClient.exe+AD7D8F - 48 8B CB              - mov rcx,rbx



class QuestClientManager(DynamicMemoryObject):
    async def quest_data(self) -> dict[int, QuestData]:
        return await self.read_std_map(0x80, QuestData)
