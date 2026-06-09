from core.config import AppConfig, RunConfig, IssueMetadata, PlatformConfig
from core.image_renderer import ImageRenderer

issue = IssueMetadata(
    id="123",
    issue_number="25",
    name="Tremors",
    cover_date="1994-10-01",
    description="A new vigilante, Spawn, faces off against Tremor...",
    image_url=None,
    volume_name="Spawn",
    credits=[
        {"name": "Todd McFarlane", "role": "writer"},
        {"name": "Marc Silvestri", "role": "penciler"}
    ]
)

run_config = RunConfig(
    title="Spawn",
    publisher="Image",
    volume_number="",
    start_year=1994,
    end_year=1994,
    custom_footer_text="covertnerdpodcast",
)

platform_config = PlatformConfig(
    name="Instagram",
    directory_prefix="ig",
    social_post_filename_prefix="ig",
    social_post_filename_suffix="",
    description_word_limit=50
)

import PIL.Image as Image
import PIL.ImageDraw as ImageDraw

img = Image.new('RGB', (550, 800), color=(100, 100, 100))
draw = ImageDraw.Draw(img)
draw.text((200, 400), "FAKE COVER", fill=(255, 255, 255))
img.save("test_cover.jpg")

renderer = ImageRenderer()
renderer.render_social_image(run_config, platform_config, issue, "test_cover.jpg", "test_output.jpg")
print("Saved to test_output.jpg")
