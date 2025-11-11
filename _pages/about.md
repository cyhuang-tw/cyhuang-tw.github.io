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

I am a first-year Ph.D. student at Language Technologies Institute, Carnegie Mellon University, advised by [Prof. Shinji Watanabe](https://sites.google.com/view/shinjiwatanabe). My research interest mainly focuses on speech and language, and recently I am interested developing spoken language models. Previously, I was a research assistant at Speech Processing Lab, National Taiwan University. I was also a R&D engineer at MediaTek Inc. working on computer vision tasks such as super-solution and frame-rate conversion (MEMC). I designed and trained lightweight networks which can be run on mobile devices in real-time. I received the M.S. degree from National Taiwan University in 2021. During the time, I joined the Speech Processing Laboratory led by [Prof. Lin-shan Lee](https://linshanlee.com) and [Prof. Hung-yi Lee](https://speech.ee.ntu.edu.tw/~hylee/index.php).

## Publications {#publications}

<ul>
{% for post in site.publications reversed %}
  {% include archive-single-publication-cv.html %}
{% endfor %}
</ul>

## Honors {#honors}

<ul>
{% for post in site.honors reversed %}
  {% include archive-single-honor-cv.html %}
{% endfor %}
</ul>
