#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""生成 examples/ 的公有领域源 PDF（美国宪法第一修正案、第十四修正案§1、42 U.S.C. § 1983）。

用途：为端到端示例提供可再生的英文法律文本源文件。所有文本均为美国联邦法律文本，
属公有领域（美国联邦政府作品不享版权）。

用法：python examples/make_source_pdf.py
输出：examples/constitution_excerpt.pdf
"""
import os
import sys

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

HERE = os.path.dirname(os.path.abspath(__file__))

SECTIONS = [
    ("Amendment I", [
        "Congress shall make no law respecting an establishment of religion, or prohibiting "
        "the free exercise thereof; or abridging the freedom of speech, or of the press; or "
        "the right of the people peaceably to assemble, and to petition the Government for a "
        "redress of grievances.",
        "The several state constitutions likewise secure the free exercise of religion and the "
        "liberty of speech and of the press, and provisions of this kind have long been "
        "understood to withdraw these subjects from the sphere of legislative discretion. "
        "In the exercise of some of these rights, the people may act through assemblies and "
        "associations; in others, they act through the press, which, serving as a channel for "
        "the communication of thought, remains exempt from previous restraint, subject to "
        "liability after publication for abuses that the law may define.",
    ]),
    ("Amendment XIV, Section 1", [
        "All persons born or naturalized in the United States, and subject to the jurisdiction "
        "thereof, are citizens of the United States and of the State wherein they reside. No "
        "State shall make or enforce any law which shall abridge the privileges or immunities "
        "of citizens of the United States; nor shall any State deprive any person of life, "
        "liberty, or property, without due process of law; nor deny to any person within its "
        "jurisdiction the equal protection of the laws.",
        "The clause last cited, the equal protection clause, has been the foundation of a large "
        "body of doctrine. Its command is addressed to the States, and it operates to restrain "
        "unreasonable classifications in the exercise of state power, whether that power is "
        "exercised by the legislature, by the courts, or by executive officers.",
    ]),
    ("42 U.S.C. § 1983 — Civil action for deprivation of rights", [
        "Every person who, under color of any statute, ordinance, regulation, custom, or "
        "usage, of any State or Territory or the District of Columbia, subjects, or causes to "
        "be subjected, any citizen of the United States or other person within the jurisdiction "
        "thereof to the deprivation of any rights, privileges, or immunities secured by the "
        "Constitution and laws, shall be liable to the party injured in an action at law, suit "
        "in equity, or other proper proceeding for redress, except that in any action brought "
        "against a judicial officer for an act or omission taken in such officer's judicial "
        "capacity, injunctive relief shall not be granted unless a declaratory decree was "
        "violated or declaratory relief was unavailable.",
        "When a plaintiff invokes 42 U.S.C. § 1983, the court must identify the specific "
        "federal right allegedly deprived, determine whether the defendant acted under color "
        "of state law, and then consider any defenses that may defeat liability, including "
        "good-faith immunities recognized for certain categories of defendants.",
    ]),
]


def main():
    styles = {
        "h": ParagraphStyle("h", fontName="Times-Bold", fontSize=13, leading=17,
                            spaceBefore=14, spaceAfter=8),
        "b": ParagraphStyle("b", fontName="Times-Roman", fontSize=11, leading=16,
                            spaceAfter=8),
    }
    out = os.path.join(HERE, "constitution_excerpt.pdf")
    doc = SimpleDocTemplate(out, pagesize=letter,
                            leftMargin=1 * inch, rightMargin=1 * inch,
                            topMargin=0.9 * inch, bottomMargin=0.9 * inch,
                            title="Public-Domain Legal Texts — Excerpt for Translation Demo")
    story = [Paragraph("Excerpts from United States Federal Law (Public Domain)", styles["h"]),
             Paragraph("This document collects three public-domain texts used to demonstrate "
                       "the English-to-Chinese legal translation pipeline: the First Amendment "
                       "to the United States Constitution, Section 1 of the Fourteenth Amendment, "
                       "and 42 U.S.C. § 1983.", styles["b"])]
    for title, paras in SECTIONS:
        story.append(Paragraph(title, styles["h"]))
        for p in paras:
            story.append(Paragraph(p, styles["b"]))
    doc.build(story)
    print("written:", out)


if __name__ == "__main__":
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = __import__("io").TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    main()
