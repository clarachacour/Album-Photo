import React from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { localePath } from "@/lib/localePath";

/** A page's address in the visitor's language ("/faq" → "/fr/faq" in French). */
export function useLocalePath() {
  const { i18n } = useTranslation();
  return (to) => localePath(to, i18n.resolvedLanguage);
}

/** A link to a public page, to its version in the visitor's language. */
export default function LocalLink({ to, ...props }) {
  const lp = useLocalePath();
  return <Link to={lp(to)} {...props} />;
}
