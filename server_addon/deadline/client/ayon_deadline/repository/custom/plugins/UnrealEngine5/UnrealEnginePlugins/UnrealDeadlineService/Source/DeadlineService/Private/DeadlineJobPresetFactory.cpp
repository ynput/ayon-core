// Copyright Epic Games, Inc. All Rights Reserved.

#include "DeadlineJobPresetFactory.h"

#include "DeadlineJobPreset.h"

#include "AssetTypeCategories.h"

UDeadlineJobPresetFactory::UDeadlineJobPresetFactory()
{
	bCreateNew = true;
	bEditAfterNew = false;
	bEditorImport = false;
	SupportedClass = UDeadlineJobPreset::StaticClass();
}
	
 UObject* UDeadlineJobPresetFactory::FactoryCreateNew(UClass* Class, UObject* InParent, FName Name, EObjectFlags Flags, UObject* Context, FFeedbackContext* Warn)
{
	return NewObject<UDeadlineJobPreset>(InParent, Class, Name, Flags);	
}

FText UDeadlineJobPresetFactory::GetDisplayName() const
{
	return NSLOCTEXT("AssetTypeActions", "AssetTypeActions_DeadlineJobPreset", "Deadline Job Preset");
}

uint32 UDeadlineJobPresetFactory::GetMenuCategories() const
{
	return EAssetTypeCategories::Misc;
}
