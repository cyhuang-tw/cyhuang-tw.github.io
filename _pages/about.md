---
permalink: /
title: ""
excerpt: "About me"
author_profile: true
redirect_from: 
  - /about/
  - /about.html
---

{% include base_path %}

## Bio {#bio}

I am a second-year Ph.D. student at Language Technologies Institute, Carnegie Mellon University, advised by [Prof. Shinji Watanabe](https://sites.google.com/view/shinjiwatanabe). My research interest mainly focuses on speech and language, and recently I have been interested in developing spoken language models. Previously, I was a research assistant at Speech Processing Lab, National Taiwan University. I was also an R&D engineer at MediaTek Inc., where I designed and trained lightweight networks for super-resolution and frame-rate conversion (MEMC) that run on mobile devices in real time. I received the M.S. degree from National Taiwan University in 2021. During the time, I joined the Speech Processing Laboratory led by [Prof. Lin-shan Lee](https://linshanlee.com) and [Prof. Hung-yi Lee](https://speech.ee.ntu.edu.tw/~hylee/index.php).

## Publications {#publications}

<p class="pub-scholar-link"><a href="{{ site.author.googlescholar }}">See all publications on Google Scholar &rarr;</a></p>

{% assign pubs = site.publications | sort: "date" | reverse %}
{% assign pub_years = pubs | group_by_exp: "post", "post.date | date: '%Y'" %}
{% for year in pub_years %}
<h3 class="pub-year">{{ year.name }}</h3>
<ul>
{% for post in year.items %}
  {% include archive-single-publication-cv.html %}
{% endfor %}
</ul>
{% endfor %}

## Honors {#honors}

<ul>
{% for post in site.honors reversed %}
  {% include archive-single-honor-cv.html %}
{% endfor %}
</ul>
