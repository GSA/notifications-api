import ast
import unicodedata

from regex import regex


class SanitiseText:
    ALLOWED_CHARACTERS = set()

    REPLACEMENT_CHARACTERS = {
        "–": "-",  # EN DASH (U+2013)
        "—": "-",  # EM DASH (U+2014)
        "…": "...",  # HORIZONTAL ELLIPSIS (U+2026)
        "‘": "'",  # LEFT SINGLE QUOTATION MARK (U+2018)
        "’": "'",  # RIGHT SINGLE QUOTATION MARK (U+2019)
        "“": '"',  # LEFT DOUBLE QUOTATION MARK (U+201C)
        "”": '"',  # RIGHT DOUBLE QUOTATION MARK (U+201D)
        "\u180E": "",  # Mongolian vowel separator
        "\u200B": "",  # zero width space
        "\u200C": "",  # zero width non-joiner
        "\u200D": "",  # zero width joiner
        "\u2060": "",  # word joiner
        "\uFEFF": "",  # zero width non-breaking space
        "\u00A0": " ",  # NON BREAKING WHITE SPACE (U+200B)
        "\t": " ",  # TAB
    }

    @classmethod
    def encode(cls, content):
        return "".join(cls.encode_char(char) for char in content)

    @classmethod
    def get_non_compatible_characters(cls, content):
        """
        Given an input string, return a set of non compatible characters.

        This follows the same rules as `cls.encode`, but returns just the characters that encode would replace with `?`
        """
        return set(
            c
            for c in content
            if c not in cls.ALLOWED_CHARACTERS
            and cls.is_extended_language(c) is False
            and cls.downgrade_character(c) is None
        )

    @staticmethod
    def get_unicode_char_from_codepoint(codepoint):
        """
        Given a unicode codepoint (eg 002E for '.', 0061 for 'a', etc), return that actual unicode character.

        unicodedata.decomposition returns strings containing codepoints, so we need to eval them ourselves
        """
        # lets just make sure we aren't evaling anything weird
        if not set(codepoint) <= set("0123456789ABCDEF") or not len(codepoint) == 4:
            raise ValueError("{} is not a valid unicode codepoint".format(codepoint))
        return ast.literal_eval('"\\u{}"'.format(codepoint))

    @classmethod
    def downgrade_character(cls, c):
        """
        Attempt to downgrade a non-compatible character to the allowed character set. May downgrade to multiple
        characters, eg `… -> ...`

        Will return None if character is either already valid or has no known downgrade
        """
        decomposed = unicodedata.decomposition(c)
        if decomposed != "" and "<" not in decomposed:
            # decomposition lists the unicode code points a character is made up of, if it's made up of multiple
            # points. For example the á character returns '0061 0301', as in, the character a, followed by a combining
            # acute accent. The decomposition might, however, also contain a decomposition mapping in angle brackets.
            # For a full list of the types, see here: https://www.compart.com/en/unicode/decomposition.
            # If it's got a mapping, we're not sure how best to downgrade it, so just see if it's in the
            # REPLACEMENT_CHARACTERS map. If not, then it's probably a letter with a modifier, eg á
            # ASSUMPTION: The first character of a combined unicode character (eg 'á' == '0061 0301')
            # will be the ascii char
            return cls.get_unicode_char_from_codepoint(decomposed.split()[0])
        else:
            # try and find a mapping (eg en dash -> hyphen ('–': '-')), else return None
            return cls.REPLACEMENT_CHARACTERS.get(c)

    @classmethod
    def is_japanese(cls, value):
        if regex.search(r"([\p{IsHan}\p{IsHiragana}\p{IsKatakana}]+)", value):
            return True
        return False

    @classmethod
    def is_chinese(cls, value):
        # This range supports all "CJK Unified Ideoglyphs"
        # It may be missing some rare/historic characters that are not in common use
        if regex.search(r"[\u4e00-\u9fff]+", value) or value in [
            "。",
            "、",
            "：",
            "？",
            "！",
            ";",
            "(",
            ")",
            "“",
            "”",
            "，",
        ]:
            return True
        return False

    @classmethod
    def is_arabic(cls, value):
        # For some reason, the python definition of Arabic (IsArabic) doesn't include
        # some standard diacritics, so add them here.
        if (
            regex.search(r"\p{IsArabic}", value)
            or regex.search(r"[\uFE70]+", value)
            or regex.search(r"[\u064B]+", value)
            or regex.search(r"[\u064F]+", value)
        ):
            return True
        return False

    @classmethod
    def is_punjabi(cls, value):
        # Gukmukhi script or Shahmukhi script

        if (
            regex.search(r"[\u0A00-\u0A7F]+", value)
            or regex.search(r"[\u0600-\u06FF]+", value)
            or regex.search(r"[\u0750-\u077F]+", value)
            or regex.search(r"[\u08A0-\u08FF]+", value)
            or regex.search(r"[\uFB50-\uFDFF]+", value)
            or regex.search(r"[\uFE70-\uFEFF]+", value)
            or regex.search(r"[\u0900-\u097F]+", value)
        ):
            return True
        return False

    @classmethod
    def _is_extended_language_group_one(cls, value):
        if regex.search(r"\p{IsHangul}", value):  # Korean
            return True
        elif regex.search(r"\p{IsCyrillic}", value):
            return True
        elif SanitiseText.is_arabic(value):
            return True
        elif regex.search(r"\p{IsArmenian}", value):
            return True
        elif regex.search(r"\p{IsBengali}", value):
            return True
        elif SanitiseText.is_punjabi(value):
            return True
        return False

    @classmethod
    def _is_extended_language_group_two(cls, value):
        if (
            regex.search(r"\p{IsBuhid}", value)
            or regex.search(r"\p{IsCanadian_Aboriginal}", value)
            or regex.search(r"\p{IsCherokee}", value)
            or regex.search(r"\p{IsDevanagari}", value)
            or regex.search(r"\p{IsEthiopic}", value)
            or regex.search(r"\p{IsGeorgian}", value)
        ):
            return True
        return False

    @classmethod
    def _is_extended_language_group_three(cls, value):
        if (
            regex.search(r"\p{IsGreek}", value)
            or regex.search(r"\p{IsGujarati}", value)
            or regex.search(r"\p{IsHanunoo}", value)
            or regex.search(r"\p{IsHebrew}", value)
            or regex.search(r"\p{IsLimbu}", value)
            or regex.search(r"\p{IsKannada}", value)
        ):
            return True
        return False

    @classmethod
    def _is_extended_language_group_four(cls, value):
        if regex.search(
            r"([\p{IsKhmer}\p{IsLao}\p{IsMongolian}\p{IsMyanmar}\p{IsTibetan}\p{IsYi}]+)",
            value,
        ):
            return True

        if regex.search(
            r"([\p{IsOgham}\p{IsOriya}\p{IsSinhala}\p{IsSyriac}\p{IsTagalog}]+)", value
        ):
            return True

        if regex.search(
            r"([\p{IsTagbanwa}\p{IsTaiLe}\p{IsTamil}\p{IsTelugu}\p{IsThaana}\p{IsThai}]+)",
            value,
        ):
            return True

        # Vietnamese
        if regex.search(
            r"\b\S*[AĂÂÁẮẤÀẰẦẢẲẨÃẴẪẠẶẬĐEÊÉẾÈỀẺỂẼỄẸỆIÍÌỈĨỊOÔƠÓỐỚÒỒỜỎỔỞÕỖỠỌỘỢUƯÚỨÙỪỦỬŨỮỤỰYÝỲỶỸỴAĂÂÁẮẤÀẰẦẢẲẨÃẴẪẠẶẬĐEÊÉẾÈỀẺỂẼỄẸỆIÍÌỈĨỊOÔƠÓỐỚÒỒỜỎỔỞÕỖỠỌỘỢUƯÚỨÙỪỦỬŨỮỤỰYÝỲỶỸỴAĂÂÁẮẤÀẰẦẢẲẨÃẴẪẠẶẬĐEÊÉẾÈỀẺỂẼỄẸỆIÍÌỈĨỊOÔƠÓỐỚÒỒỜỎỔỞÕỖỠỌỘỢUƯÚỨÙỪỦỬŨỮỤỰYÝỲỶỸỴAĂÂÁẮẤÀẰẦẢẲẨÃẴẪẠẶẬĐEÊÉẾÈỀẺỂẼỄẸỆIÍÌỈĨỊOÔƠÓỐỚÒỒỜỎỔỞÕỖỠỌỘỢUƯÚỨÙỪỦỬŨỮỤỰYÝỲỶỸỴAĂÂÁẮẤÀẰẦẢẲẨÃẴẪẠẶẬĐEÊÉẾÈỀẺỂẼỄẸỆIÍÌỈĨỊOÔƠÓỐỚÒỒỜỎỔỞÕỖỠỌỘỢUƯÚỨÙỪỦỬŨỮỤỰYÝỲỶỸỴAĂÂÁẮẤÀẰẦẢẲẨÃẴẪẠẶẬĐEÊÉẾÈỀẺỂẼỄẸỆIÍÌỈĨỊOÔƠÓỐỚÒỒỜỎỔỞÕỖỠỌỘỢUƯÚỨÙỪỦỬŨỮỤỰYÝỲỶỸỴđa-zA-Z]+\S*\b",  # noqa
            value,
        ):
            return True

        # Turkish
        if regex.search(r"\b\S*[a-zA-ZçğışöüÇĞİŞÖÜ]+\S*\b", value):
            return True

        return False

    @classmethod
    def is_extended_language(cls, value):
        """
        Languages are combined in groups to handle cyclomatic complexity warnings
        """
        if cls._is_extended_language_group_one(value):
            return True
        if cls._is_extended_language_group_two(value):
            return True
        if cls._is_extended_language_group_three(value):
            return True
        if cls.is_japanese(value):
            return True
        if cls._is_extended_language_group_four(value):
            return True
        if cls.is_chinese(value):
            return True

        return False

    @classmethod
    def encode_char(cls, c):
        """
        Given a single unicode character, return a compatible character from the allowed set.
        """
        # char is a good character already - return that native character.
        if c in cls.ALLOWED_CHARACTERS:
            return c
        elif cls.is_extended_language(c):
            return c
        else:
            c = cls.downgrade_character(c)
            return c if c is not None else "?"


class SanitiseSMS(SanitiseText):
    """
    Given an input string, makes it GSM and Welsh character compatible. This involves removing all non-gsm characters by
    applying the following rules
    * characters within the GSM character set (https://en.wikipedia.org/wiki/GSM_03.38)
      and extension character set are kept

    * Welsh characters not included in the default GSM character set are kept

    * characters with sensible downgrades are replaced in place
        * characters with diacritics (accents, umlauts, cedillas etc) are replaced with their base character, eg é -> e
        * en dash and em dash (– and —) are replaced with hyphen (-)
        * left/right quotation marks (‘, ’, “, ”) are replaced with ' and "
        * zero width spaces (sometimes used to stop eg "gov.uk" linkifying) are removed
        * tabs are replaced with a single space

    * any remaining unicode characters (eg chinese/cyrillic/glyphs/emoji) are replaced with ?
    """

    WELSH_DIACRITICS = set(
        "àèìòùẁỳ"
        "ÀÈÌÒÙẀỲ"  # grave
        "áéíóúẃý"
        "ÁÉÍÓÚẂÝ"  # acute
        "äëïöüẅÿ"
        "ÄËÏÖÜẄŸ"  # diaeresis
        "âêîôûŵŷ"
        "ÂÊÎÔÛŴŶ"  # carets
    )

    EXTENDED_GSM_CHARACTERS = set("^{}\\[~]|€")

    GSM_CHARACTERS = (
        set(
            "@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞ\x1bÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?"
            + "¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà"
        )
        | EXTENDED_GSM_CHARACTERS
    )

    ALLOWED_CHARACTERS = GSM_CHARACTERS | WELSH_DIACRITICS
    # some welsh characters are in GSM and some aren't - we need to distinguish between these for counting fragments
    WELSH_NON_GSM_CHARACTERS = WELSH_DIACRITICS - GSM_CHARACTERS


class SanitiseASCII(SanitiseText):
    """
    As SMS above, but the allowed characters are printable ascii, from character range 32 to 126 inclusive.
    [chr(x) for x in range(32, 127)]
    """

    ALLOWED_CHARACTERS = set(
        " !\"#$%&'()*+,-./0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        + "[\\]^_`abcdefghijklmnopqrstuvwxyz{|}~"
    )
