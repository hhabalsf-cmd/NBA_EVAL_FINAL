-- Server-side registration cap (early access).
--
-- The frontend also checks the profile count before calling signUp, but that
-- is UX only — anyone with the anon key can call auth.signUp directly. This
-- trigger is the actual enforcement: profile rows are created by the
-- handle_new_user trigger on auth.users inside the signup transaction, so
-- raising here aborts the whole signup.
--
-- Applied live on 2026-08-06.

CREATE OR REPLACE FUNCTION public.enforce_registration_cap()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  max_accounts CONSTANT integer := 10;
  profile_count integer;
BEGIN
  -- Serialize concurrent signups so two inserts can't both read count = 9
  PERFORM pg_advisory_xact_lock(hashtext('registration_cap'));

  SELECT COUNT(*) INTO profile_count FROM public.profiles;
  IF profile_count >= max_accounts THEN
    RAISE EXCEPTION 'REGISTRATION_CLOSED'
      USING HINT = 'Early-access account cap reached';
  END IF;

  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_registration_cap ON public.profiles;
CREATE TRIGGER trg_registration_cap
  BEFORE INSERT ON public.profiles
  FOR EACH ROW EXECUTE FUNCTION public.enforce_registration_cap();
