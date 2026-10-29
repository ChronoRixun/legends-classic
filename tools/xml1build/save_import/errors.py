"""Stable refusal codes, independent of the builder's event transport."""

MESSAGES = {
    'INPUT': 'Choose the extracted Xbox save folder containing save.dat.',
    'MULTIPLE': 'This folder contains more than one campaign. Choose the one to import.',
    'DAMAGED': 'This save is incomplete or damaged. Your original has not been changed.',
    'VERSION': "This game's save version is not supported yet.",
    'RECOMP_VERSION': 'This XML1-recomp save version is not supported yet.',
    'DISK_VERSION': 'This HDD image format or feature is not supported. No source files were changed.',
    'DISK_DAMAGED': 'This HDD image has invalid or incomplete disk structures. No source files were changed.',
    'IDENTITY': 'A saved hero, power or item cannot be identified safely. No import was created.',
    'CONTEXT': 'This campaign needs a supported mission checkpoint before it can be imported.',
    'SIDE_MISSION': 'Finish the flashback or side mission, save again, then import that save.',
    'BUILD': 'This installation needs W2 saves, the XML1 item economy and the XML1 XP curve.',
    'CAPACITY': 'This installation cannot preserve all of the saved items or progression.',
    'CHANGED': 'The save or installation changed after the preview. Analyze it again.',
    'SLOT': 'That slot already contains a save. Choose an empty slot.',
    'BUSY': 'Close the game and any other save importer before importing a campaign.',
    'INFERRED': 'This import needs the listed experimental approximations. Review them before opting in.',
    'UNVALIDATED': 'This checkpoint has not passed real-save and native-loader acceptance yet.',
    'MERGE': 'These source unlocks cannot be merged safely yet. No profile was changed.',
}


class ImportRefusal(ValueError):
    def __init__(self, code, reason='', **detail):
        self.code = 'E_XML1_' + code
        self.msg = MESSAGES[code]
        self.detail = dict(detail, reason=reason) if reason else detail
        super().__init__(self.msg)
