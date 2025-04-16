import pytest

from notifications_utils.sanitise_text import SanitiseASCII, SanitiseSMS, SanitiseText

params, ids = zip(
    (("a", "a"), "ascii char (a)"),
    # ascii control char (not in GSM)
    (("\t", " "), "ascii control char not in gsm (tab)"),
    # TODO we support lots of languages now not in the GSM charset so maybe make this 'downgrading' go away
    # TODO for now comment out this line because it directly conflicts with support for Turkish
    # these are not in GSM charset so are downgraded
    # (("ç", "c"), "decomposed unicode char (C with cedilla)"),
    # these unicode chars should change to something completely different for compatibility
    # (("–", "-"), "compatibility transform unicode char (EN DASH (U+2013)"),
    # (("—", "-"), "compatibility transform unicode char (EM DASH (U+2014)"),
    (
        ("…", "..."),
        "compatibility transform unicode char (HORIZONTAL ELLIPSIS (U+2026)",
    ),
    (("\u200b", ""), "compatibility transform unicode char (ZERO WIDTH SPACE (U+200B)"),
    (
        ("‘", "'"),
        "compatibility transform unicode char (LEFT SINGLE QUOTATION MARK (U+2018)",
    ),
    (
        ("’", "'"),
        "compatibility transform unicode char (RIGHT SINGLE QUOTATION MARK (U+2019)",
    ),
    # Conflict with Chinese quotes
    # (
    #    ("“", '"'),
    #    "compatibility transform unicode char (LEFT DOUBLE QUOTATION MARK (U+201C)	",
    # ),
    # (
    #    ("”", '"'),
    #    "compatibility transform unicode char (RIGHT DOUBLE QUOTATION MARK (U+201D)",
    # ),
    (("\xa0", " "), "nobreak transform unicode char (NO-BREAK SPACE (U+00A0))"),
    # this unicode char is not decomposable
    (("😬", "?"), "undecomposable unicode char (grimace emoji)"),
    (("↉", "?"), "vulgar fraction (↉) that we do not try decomposing"),
)


@pytest.mark.parametrize(("char", "expected"), params, ids=ids)
@pytest.mark.parametrize("cls", [SanitiseSMS, SanitiseASCII])
def test_encode_chars_the_same_for_ascii_and_sms(char, expected, cls):
    assert cls.encode_char(char) == expected


params, ids = zip(
    # ascii control chars are allowed in GSM but not in ASCII
    (("\n", "\n", "?"), "ascii control char in gsm (newline)"),
    (("\r", "\r", "?"), "ascii control char in gsm (return)"),
    # These characters are present in GSM but not in ascii
    (("à", "à", "a"), "non-ascii gsm char (a with accent)"),
    (("€", "€", "?"), "non-ascii gsm char (euro)"),
    # These characters are Welsh characters that are not present in GSM
    (("â", "â", "a"), "non-gsm Welsh char (a with hat)"),
    (("Ŷ", "Ŷ", "Y"), "non-gsm Welsh char (capital y with hat)"),
    (("ë", "ë", "e"), "non-gsm Welsh char (e with dots)"),
    # (("Ò", "Ò", "O"), "non-gsm Welsh char (capital O with grave accent)"),  # conflicts with Vietnamese
    (("í", "í", "i"), "non-gsm Welsh char (i with accent)"),
)


@pytest.mark.parametrize(("char", "expected_sms", "expected_ascii"), params, ids=ids)
def test_encode_chars_different_between_ascii_and_sms(
    char, expected_sms, expected_ascii
):
    assert SanitiseSMS.encode_char(char) == expected_sms
    assert SanitiseASCII.encode_char(char) == expected_ascii


@pytest.mark.parametrize(
    ("codepoint", "char"),
    [
        ("0041", "A"),
        ("0061", "a"),
    ],
)
def test_get_unicode_char_from_codepoint(codepoint, char):
    assert SanitiseText.get_unicode_char_from_codepoint(codepoint) == char


@pytest.mark.parametrize(
    "bad_input", ["", "GJ", "00001", '0001";import sys;sys.exit(0)"']
)
def test_get_unicode_char_from_codepoint_rejects_bad_input(bad_input):
    with pytest.raises(ValueError):  # noqa PT011
        SanitiseText.get_unicode_char_from_codepoint(bad_input)


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ("Łōdź", "?odz"),
        (
            "The quick brown fox jumps over the lazy dog",
            "The quick brown fox jumps over the lazy dog",
        ),
    ],
)
def test_encode_string(content, expected):
    assert SanitiseSMS.encode(content) == expected
    assert SanitiseASCII.encode(content) == expected


@pytest.mark.parametrize(
    ("content", "cls", "expected"),
    [
        ("The quick brown fox jumps over the lazy dog", SanitiseSMS, set()),
        (
            "The “quick” brown fox has some downgradable characters\xa0",
            SanitiseSMS,
            set(),
        ),
        ("Need more 🐮🔔", SanitiseSMS, {"🐮", "🔔"}),
        ("Ŵêlsh chârâctêrs ârê cômpâtîblê wîth SanitiseSMS", SanitiseSMS, set()),
        ("Lots of GSM chars that arent ascii compatible:\n\r€", SanitiseSMS, set()),
        (
            "Lots of GSM chars that arent ascii compatible:\n\r€",
            SanitiseASCII,
            {"\n", "\r", "€"},
        ),
        ("Αυτό είναι ένα τεστ", SanitiseSMS, set()),
        ("。、“”()：;？！", SanitiseSMS, set()),  # Chinese punctuation
    ],
)
def test_sms_encoding_get_non_compatible_characters(content, cls, expected):
    assert cls.get_non_compatible_characters(content) == expected


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ("이것은 테스트입니다", True),  # Korean
        ("Αυτό είναι ένα τεστ", True),  # Greek
        ("Это проверка", True),  # Russian
        ("นี่คือการทดสอบ", True),  # Thai
        ("இது ஒரு சோதனை", True),  # Tamil
        ("これはテストです", True),  # Japanese
        ("Đây là một bài kiểm tra", True),  # Vietnamese
        ("𐤓𐤓𐤓𐤈𐤆", False),  # Phoenician
        ("这是一次测试", True),  # Mandarin (Simplified)
        ("Bunda Türkçe karakterler var", True),  # Turkish
        (
            "盾牌镍币是第一种采用白铜制作的5美分硬币，由詹姆斯·B·朗埃克设计，从1866年发行到1883年再由自由女神头像镍币取代。",
            True,
        ),  # Chinese from wikipedia 1
        (
            "国际志愿者日為每年的12月5日，它是由联合国大会在1985年12月17日通过的A/RES/40/212决议[1]上确定的[2]。",
            True,
        ),  # Chinese from wikipedia 2
        (
            "哪一種多邊形內部至少存在一個可以看見多邊形所有邊界和所有內部區域的點？",
            True,
        ),  # Chinese from wikipedia 3
        (
            """都柏林在官方城市邊界內的人口是大約495,000人（愛爾蘭中央統計處2002年人口調查），
            然而這種統計已經沒有什麼太大的意義，因為都柏林的市郊地區和衛星城鎮已經大幅地發展與擴張。""",
            True,
        ),  # Chinese from wikipedia 4
        (
            "一名是Dubh Linn（愛爾蘭語，意為「黑色的水池」）的英國習語。當然也有人質疑這語源。",
            True,
        ),  # Chinese from wikipedia 5
        (
            "都柏林拥有世界闻名的文学历史，曾经产生过许多杰出的文学家，例如诺贝尔文学奖得主威廉·巴特勒·叶芝、蕭伯納和塞繆爾·貝克特。",
            True,
        ),  # Chinese from wikipedia 6
        (
            "愛爾蘭國家博物館的四个分馆中有三個分館都位於都柏林：考古学分馆在基尔代尔街，装饰艺术和历史分馆在柯林斯军营，而自然史分馆在梅林街[12]。",
            True,
        ),  # Chinese from wikipedia 7
        (
            "從17世紀開始，城市在寬闊街道事務委員會的幫助下開始迅速擴張。乔治亚都柏林曾一度是大英帝國僅次於倫敦的第二大城市。",
            True,
        ),  # Chinese from wikipedia 8
        (
            "一些著名的都柏林街道建築仍以倒閉前在此經營的酒吧和商業公司命名。",
            True,
        ),  # Chinese from wikipedia 9
        (
            "1922年，隨著愛爾蘭的分裂，都柏林成為愛爾蘭自由邦（1922年–1937年）的首都。現在則為愛爾蘭共和國的首都。",
            True,
        ),  # Chinese from wikipedia 10
        (
            """Dưới đây là danh sách tất cả các tên người dùng hiện đang có
            tại Wikipedia, hoặc những tên người dùng trong một nhóm chỉ định. """,
            True,
        ),  # Vietnamese from wikipedia 1
        (
            """Các bảo quản viên đảm nhận những trách nhiệm này với tư cách là tình
            nguyện viên sau khi trải qua quá trình xem xét của cộng đồng. """,
            True,
        ),  # Vietnamese from wikipedia 2
        (
            """Họ không bao giờ được yêu cầu sử dụng các công cụ của mình và không bao
            giờ được sử dụng chúng để giành lợi thế trong một cuộc tranh chấp mà họ có
            tham gia. Không nên nhầm lẫn bảo quản viên với quản trị viên hệ
            thống của Wikimedia ("sysadmins").""",
            True,
        ),  # Vietnamese from wikipedia 3
        (
            "Để đạt được mục tiêu chung đó, Wikipedia đề ra một số quy định và hướng dẫn. ",
            True,
        ),  # Vietnamese from wikipedia 4
        ("Wikipedia là một bách khoa toàn thư. ", True),  # Vietnamese from wikipedia 5
        (
            "Phải đảm bảo bài viết mang lại ích lợi cho độc giả (coi độc giả là yếu tố quan trọng khi viết bài)",
            True,
        ),  # Vietnamese from wikipedia 6
        (
            """Bài viết ở Wikipedia có thể chứa đựng từ ngữ và hình ảnh gây khó chịu
            nhưng chỉ vì mục đích tốt đẹp. Không cần thêm vào phủ định trách nhiệm.""",
            True,
        ),  # Vietnamese from wikipedia 7
        (
            "Đừng sử dụng hình ảnh mà chỉ có thể xem được chính xác với công cụ 3D.",
            True,
        ),  # Vietnamese from wikipedia 8
        (
            """Trích dẫn bất cứ nôi dung tranh luận gốc nào cũng nên có liên quan
            đến tranh luận đó (hoặc minh họa cho phong cách) và chỉ nên dài vừa đủ.""",
            True,
        ),  # Vietnamese from wikipedia 9
        (
            """Không tung tin vịt, thông tin sai lệch hoặc nội dung không kiểm chứng được vào bài viết.
            Tuy nhiên, những bài viết về những tin vịt nổi bật được chấp nhận.""",
            True,
        ),  # Vietnamese from wikipedia 10
        (
            "수록되어 있으며, 넘겨주기를 포함한 일반 문서 수는 1,434,776개。",
            True,
        ),  # Korean from wikipedia includes circle-period
        (
            "日本語表記にも対応するようになり[1]、徐々に日本人のユーザーも増大していった、と述べられている。",
            True,
        ),  # Japanese from wikipedia includes circle-period
        (
            "DSHS:我们发现您的账户存在潜在欺诈行为。请致电您的 EBT 卡背面的号码废止或前往当地办公室获取一个新账户。回复 “STOP(退订)” 退订",
            True,
        ),  # State of Washington Chinese Simplified
        (
            """DSHS៖ ប ើងោនកត់សម្គា ល់ប ើញក្ដរបោកប្រោស់ជាសក្ដា នុពលបៅបលើគណនីរបស់អ្នក។ សូមបៅបៅបលខ #បៅបលើខនងក្ដត
            EBT របស់អ្នក ប ើមបីបោោះបង់ ឬក៏បៅក្ដន់ក្ដរយាិ ល័ បៅកនុងតំបន់របស់អ្នក
            ប ើមបីបសនើសុំក្ដតថ្មី។ ប្លើ តបជាអ្កសរ ឈប់ ប ើមបីបញ្ឈប់""",
            True,
        ),  # State of Washington Khmer
        (
            """DSHS: 귀하의 계정 상에 사기가 일어났을 가능성이 포착되었습니다. 귀하의 EBT 카드 뒷면에있는
            번호로 전화를 걸어 취소하거나 현지 사무소로 가서 새 것을 발급 받으세요. 중단하려면중단이라고 회신하세요.""",
            True,
        ),  # State of WA Korean
        (
            """ຂ ຄໍ້ ວາມການສໍ້ໂກງທອາດເປັນໄປໄດ ໍ້ DSHS: ພວກເຮາົໄດສໍ້ງັເກດເຫນັການສໂກງທີ່ອາດເປັນໄປໄດໃໍ້ນບນັຊຂ ອງທີ່ານ.
            ໂທຫາ # ທ ຢີ່ ດາໍ້ນຫ ງັຂອງບດັ EBT ຂອງທີ່ານເພອຍກົ ເລກ ຫ ໄປຍງັຫອໍ້ງການປະຈາ ທອໍ້ງຖ ນຂອງທີ່ານ ເພີ່ອຂ
            ບດັ ໃຫມີ່ . ຕອບກບັດວໍ້ ຍ STOP (ຢຸດເຊາົ) ເພອຢຸດເຊາົ""",
            True,
        ),  # State of WA Lao
        (
            """Fariin Khiyaamo Suurtogal ah DSHS: Waxaanu ka ogaanay khiyaamo suurtogal ah akoonkaaga.
            Wax # ee ku yaal xaga danbe ee kadadhka
            EBT si aad u joojisid ama u aadid xafiiska deegaanka uguna dalbatid a new one (mid cusub).
            Ku jawaab JOOJI si aad u joojisid""",
            True,
        ),  # State of WA Somali
        (
            "إدارة الخدمات الاجتماعية والصحية في ولاية واشنطن (Washington State Department of Social and Health Services, WA DSHS): ستُجرى المقابلة الهاتفية معك المعنية بمراقبة جودة الطعام يوم xx/xx/xx الساعة 00:00 صباحًا/مساءً. قد يؤدي الفشل إلى إغلاق مخصصاتك. اتصل بالرقم 1-800-473-5661 إذا كانت لديك أسئلة.",  # noqa
            True,
        ),  # State of WA Arabic
        (
            "WA DSHS: ਤੁਹਾਡੀ ਗੁਣਵੱਤਾ ਨਿਯੰਤਰਣ ਭੋਜਨ ਫ਼ੋਨ ਇੰਟਰਵਿਊ xx/xx/xx 'ਤੇ ਸਵੇਰੇ 00:00 ਵਜੇ/ਸ਼ਾਮ 'ਤੇ ਹੈ। ਅਸਫਲਤਾ ਤੁਹਾਡੇ ਲਾਭਾਂ ਨੂੰ ਬੰਦ ਕਰਨ ਦਾ ਕਾਰਨ ਬਣ ਸਕਦੀ ਹੈ। ਸਵਾਲਾਂ ਨਾਲ 1-800-473-5661 'ਤੇ ਕਾਲ ਕਰੋ।",  # noqa
            True,
        ),  # State of WA Punjabi
        (
            "WA DSHS: ਵਿਅਕਤੀਗਤ ਭੋਜਨ ਵਿੱਚ ਤੁਹਾਡਾ ਗੁਣਵੱਤਾ ਨਿਯੰਤਰਣ ਇੰਟਰਵਿਊ xx/xx/xx 'ਤੇ ਸਵੇਰੇ 00:00 ਵਜੇ /ਸ਼ਾਮ 00:00 ਵਜੇ ਹੈ। ਅਸਫਲਤਾ ਤੁਹਾਡੇ ਲਾਭਾਂ ਨੂੰ ਬੰਦ ਕਰਨ ਦਾ ਕਾਰਨ ਬਣ ਸਕਦੀ ਹੈ। 1-800-473-5661 'ਤੇ w/ਸਵਾਲ ਨਾਲ ਕਾਲ ਕਰੋ।",  # noqa
            True,
        ),  # State of WA Punjabi
    ],
)
def test_sms_supporting_additional_languages(content, expected):
    assert SanitiseSMS.is_extended_language(content) is expected


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ("이것은 테스트입니다", set()),  # Korean
        ("Αυτό είναι ένα τεστ", set()),  # Greek
        ("Это проверка", set()),  # Russian
        ("นี่คือการทดสอบ", set()),  # Thai
        ("இது ஒரு சோதனை", set()),  # Tamil
        ("これはテストです", set()),  # Japanese
        ("Đây là một bài kiểm tra", set()),  # Vietnamese
        ("𐤓𐤓𐤓𐤈𐤆", {"𐤆", "𐤈", "𐤓"}),  # Phoenician
        ("这是一次测试", set()),  # Mandarin (Simplified)
        ("Bunda Türkçe karakterler var", set()),  # Turkish
        ("。、“”()：;？！", set()),  # Chinese punctuation
        (" ُ ُ", set()),  # Arabic diacritics
        (
            "WA DSHS: ਤੁਹਾਡੀ ਗੁਣਵੱਤਾ ਨਿਯੰਤਰਣ ਭੋਜਨ ਫ਼ੋਨ ਇੰਟਰਵਿਊ xx/xx/xx 'ਤੇ ਸਵੇਰੇ 00:00 ਵਜੇ/ਸ਼ਾਮ 'ਤੇ ਹੈ। ਅਸਫਲਤਾ ਤੁਹਾਡੇ ਲਾਭਾਂ ਨੂੰ ਬੰਦ ਕਰਨ ਦਾ ਕਾਰਨ ਬਣ ਸਕਦੀ ਹੈ। ਸਵਾਲਾਂ ਨਾਲ 1-800-473-5661 'ਤੇ ਕਾਲ ਕਰੋ।",  # noqa
            set(),
        ),  # Punjabi
        (
            "WA DSHS: ਵਿਅਕਤੀਗਤ ਭੋਜਨ ਵਿੱਚ ਤੁਹਾਡਾ ਗੁਣਵੱਤਾ ਨਿਯੰਤਰਣ ਇੰਟਰਵਿਊ xx/xx/xx 'ਤੇ ਸਵੇਰੇ 00:00 ਵਜੇ /ਸ਼ਾਮ 00:00 ਵਜੇ ਹੈ। ਅਸਫਲਤਾ ਤੁਹਾਡੇ ਲਾਭਾਂ ਨੂੰ ਬੰਦ ਕਰਨ ਦਾ ਕਾਰਨ ਬਣ ਸਕਦੀ ਹੈ। 1-800-473-5661 'ਤੇ w/ਸਵਾਲ ਨਾਲ ਕਾਲ ਕਰੋ।",  # noqa
            set(),
        ),  # more Punjabi
    ],
)
def test_get_non_compatible_characters(content, expected):
    assert SanitiseSMS.get_non_compatible_characters(content) == expected
