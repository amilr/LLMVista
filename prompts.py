
GEN_RESULTS = """
Find 10 fictional search results for the search term {}.
Be creative and approach the topic from different angles.

The result types must be one of the following:
journal - a personal journal or blog
magazine - a magazine article
forum - a forum post
personal - a personal homepage

Generate the following fictional properties for each result:
1. title
2. meta - short summary of the page
3. url - a fictional url, be creative
4. type
"""


FIND_TOPICS = """
Find 5 topics related to {} that one might write about for a {}
"""

META_JOURNAL = """
Create a 400 word blog post titled '{}' about {}.
Create a fictional persona that wrote this post.
"""

JOURNAL_1 = """
<CONTENT>
{}
</CONTENT>

<TITLE>
{}
<TITLE>

Create a full HTML page using this content with the following features.
<FEATURES>
90s Geocities design
no images
inline CSS
</FEATURE>
"""

JOURNAL_2 = """
<CONTENT>
{}
</CONTENT>

<TITLE>
{}
<TITLE>

Create a full HTML page using this content with the following features.
<FEATURES>
dark Livejournal design
A few fictional comments
no images
inline CSS
</FEATURE>
"""

JOURNAL_3 = """
<CONTENT>
{}
</CONTENT>

<TITLE>
{}
<TITLE>

Create a full HTML page using this content with the following features.
<FEATURES>
mid 2000s Wordpress design
A few fictional comments
no images
inline CSS
</FEATURE>
"""

META_EZINE = """
Create a 400 word magazine article titled '{}' about {}.
Create a fictional persona and publication that wrote this article.
"""

EZINE_1 = """
<CONTENT>
{}
</CONTENT>

<TITLE>
{}
<TITLE>

Create a full HTML page using this content with the following features.
<FEATURES>
    1.  Fixed-Width, Table-Based Layout - The page was structured using <table> elements, with a clear two- or three-column design for content, navigation, and ads.
	2.	Sans-Serif Fonts (Arial, Verdana) - The main text was in Arial or Verdana, ensuring readability on CRT monitors.
	3.	Blue Hyperlinks with Underlines - Standard blue, underlined links for navigation and article references.
	4.	White Background with Gray or Light Blue Accents - A clean, high-contrast look for readability, often with a thin gray border around the main content.
	5.	Bold Headlines in Larger Fonts - Article titles were bold, black, and bigger than the body text, often using <h2> or <h3> elements.
	6.	Navigation Sidebar on the Left - A vertical sidebar with links to other categories
 	7.	Small “Byline” and Date Below the Title - The author's name and date appeared in a smaller, italicized font below the headline.
	8.	Blockquote or Indented Callouts - Important quotes or key takeaways were indented or put in a light gray box.
	9.	Simple Footer with Copyright & Contact Links - The bottom had a basic copyright notice, privacy policy, and email contact.
	10.	Minimal JavaScript or Interactivity - No heavy animations—just static HTML with some rollover effects for navigation.
    11. No images!
</FEATURE>
"""

EZINE_2 = """
<CONTENT>
{}
</CONTENT>

<TITLE>
{}
<TITLE>

Create a full HTML page using this content with the following features.
<FEATURES>
	1.	Fixed-Width, Table-Based Layout - A structured design using <table> elements, often centered on the screen.
	2.	Bold, Futuristic Typography - Heavy use of sans-serif fonts like Helvetica and custom Wired-style fonts, sometimes in uppercase for emphasis.
	3.	High-Contrast Color Schemes - Black backgrounds with neon colors (red, green, cyan) or grayscale with splashes of bold accents.
	4.	Edgy, Minimalist Navigation - Often text-based navigation menus rather than traditional buttons, laid out in a single horizontal line.
	5.	Experimental CSS & HTML Tricks - Unconventional layout choices, text overlapping images, and creative use of <hr> dividers.
	6.	Short, Punchy Headlines - Article titles were minimalist and provocative, reflecting Wired's cyberpunk-inspired writing.
	7.	Dense, Column-Based Content - Articles were arranged in multi-column layouts, often with narrow text blocks to mimic print magazines.
	8.	Interactive Elements (But No Flash Yet) - Some early JavaScript rollovers for links or mouseover effects in navigation.
	9.	Dotted or Pixel Borders - Thin, dotted-line dividers were common, creating a “hacked” or digital feel.
    10. No images!
</FEATURE>
"""

META_FORUM = """
Create a 150 word forum post titled '{}' about {}.
Create a fictional persona that wrote this post.
"""

FORUM_1 = """
<CONTENT>
{}
</CONTENT>

<TITLE>
{}
<TITLE>

Create a full HTML page using this content with the following features.
<FEATURES>
BBForum style design
Amusing forum name at the top
A username, often styled based on rank (e.g., bold for admins, colors for mods)
Post count, join date, and user rank/title (e.g., “Newbie,” “Senior Member”)
Forums had fixed-width layouts with light or dark themes (Blue, Grey, or Black)
Alternating row colors to differentiate posts
Basic buttons like Reply, Quote, Report, and Edit
no images
inline CSS
3-5 fictional replies
</FEATURE>
"""

META_PERSONAL = """
Create a personal page titled '{}' about {}.
Create a fictional persona that created this page.
"""

PERSONAL_1 = """
<CONTENT>
{}
</CONTENT>

<TITLE>
{}
<TITLE>

Create a full HTML page using this content with the following features.
<FEATURES>
Late 90s style personal homepage
Featured things like “About Me” sections, guestbooks, and visitor counters.
inline CSS
</FEATURE>
"""