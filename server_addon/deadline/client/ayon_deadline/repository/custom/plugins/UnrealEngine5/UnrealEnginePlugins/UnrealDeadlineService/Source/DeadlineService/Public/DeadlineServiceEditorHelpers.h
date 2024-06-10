// Copyright Epic Games, Inc. All Rights Reserved.

#pragma once

#include "DeadlineJobPreset.h"
#include "DeadlineServiceEditorSettings.h"
#include "Kismet/BlueprintFunctionLibrary.h"

#include "DeadlineServiceEditorHelpers.generated.h"

/**
* Using UCLASS instead of a namespace because we need reflection to call from python
*/
UCLASS()
class DEADLINESERVICE_API UDeadlineServiceEditorHelpers : public UBlueprintFunctionLibrary
{
	GENERATED_BODY()
	
	/**
	 * Returns the given Deadline job info struct a TMap<FString,FString>, python compatible
	 * Excludes "PluginInfo". Use GetPluginInfo to collect this separately.
	 */
	UFUNCTION(BlueprintCallable, Category = "DeadlineService")
	static TMap<FString, FString> GetDeadlineJobInfo(const FDeadlineJobPresetStruct& JobPresetStruct)
	{
		TMap<FString, FString> ReturnValue = {{"Plugin", "UnrealEngine"}};

		if (const UDeadlineServiceEditorSettings* Settings = GetDefault<UDeadlineServiceEditorSettings>())
		{
			ReturnValue["Plugin"] = Settings->PluginName;
		}
		
		for (TFieldIterator<FProperty> PropIt(FDeadlineJobPresetStruct::StaticStruct()); PropIt; ++PropIt)
		{
			const FProperty* Property = *PropIt;
			if (!Property)
			{
				continue;
			}
			
			FName PropertyName = Property->GetFName();
			
			// Custom Handlers for specific properties prioritizing UX
			if (PropertyName.IsEqual("bSubmitJobAsSuspended"))
			{
				ReturnValue.Add("InitialStatus", JobPresetStruct.bSubmitJobAsSuspended ? "Suspended" : "Active");
			}
			else if (PropertyName.IsEqual("bMachineListIsADenyList"))
			{
				ReturnValue.Add(JobPresetStruct.bMachineListIsADenyList ? "Denylist" : "Allowlist", JobPresetStruct.MachineList);
			}
			else if (PropertyName.IsEqual("PreJobScript"))
			{
				ReturnValue.Add(PropertyName.ToString(), JobPresetStruct.PreJobScript.FilePath);
			}
			else if (PropertyName.IsEqual("PostJobScript"))
			{
				ReturnValue.Add(PropertyName.ToString(), JobPresetStruct.PostJobScript.FilePath);
			}
			else if (PropertyName.IsEqual("PreTaskScript"))
			{
				ReturnValue.Add(PropertyName.ToString(), JobPresetStruct.PreTaskScript.FilePath);
			}
			else if (PropertyName.IsEqual("PostTaskScript"))
			{
				ReturnValue.Add(PropertyName.ToString(), JobPresetStruct.PostTaskScript.FilePath);
			}
			else if (PropertyName.IsEqual("MachineList") || PropertyName.IsEqual("PluginInfo"))
			{
				// MachineList is handled above, PluginInfo is handled in a separate function
				continue;
			}
			else if (const FMapProperty* MapProperty = CastField<FMapProperty>(Property))
			{
				// Custom handler for Maps
				const void* MapValuePtr = MapProperty->ContainerPtrToValuePtr<void>(&JobPresetStruct);
				FScriptMapHelper MapHelper(MapProperty, MapValuePtr);
				for (int32 MapSparseIndex = 0; MapSparseIndex < MapHelper.GetMaxIndex(); ++MapSparseIndex)
				{
					if (MapHelper.IsValidIndex(MapSparseIndex))
					{
						const uint8* MapKeyData = MapHelper.GetKeyPtr(MapSparseIndex);
						const uint8* MapValueData = MapHelper.GetValuePtr(MapSparseIndex);

						FString KeyDataAsString;
						MapHelper.GetKeyProperty()->ExportText_Direct(KeyDataAsString, MapKeyData, MapKeyData, nullptr, PPF_None);
						FString ValueDataAsString;
						MapHelper.GetValueProperty()->ExportText_Direct(ValueDataAsString, MapValueData, MapValueData, nullptr, PPF_None);

						// Custom support for Extra Job Options. These properties are part of the top level Job Info map
						if (PropertyName.IsEqual("ExtraJobOptions"))
						{
							ReturnValue.Add(*KeyDataAsString, *ValueDataAsString);
						}
						else
						{
							FString PropertyNameAsString = FString::Printf(TEXT("%s%d"), *PropertyName.ToString(), MapSparseIndex);
							FString PropertyValueAsString = FString::Printf(TEXT("%s=%s"), *KeyDataAsString, *ValueDataAsString);
							ReturnValue.Add(PropertyNameAsString, PropertyValueAsString);
						}
						// UE_LOG(LogTemp, Warning, TEXT("%s: %s"), *PropertyNameAsString, *PropertyValueAsString);
					}
				}
			}
			else
			{
				const void* ValuePtr = Property->ContainerPtrToValuePtr<void>(&JobPresetStruct);
				FString PropertyNameAsString = PropertyName.ToString();
				FString PropertyValueAsString;
				Property->ExportText_Direct(PropertyValueAsString, ValuePtr, ValuePtr, nullptr, PPF_None);

				if (PropertyValueAsString.TrimStartAndEnd().IsEmpty())
				{
					continue;
				}

				// Sanitize bool
				if (Property->IsA(FBoolProperty::StaticClass()))
				{
					PropertyNameAsString.RemoveFromStart(TEXT("b"), ESearchCase::CaseSensitive);
					PropertyValueAsString = PropertyValueAsString.ToLower();
				}
		
				ReturnValue.Add(PropertyNameAsString, PropertyValueAsString);
				// UE_LOG(LogTemp, Warning, TEXT("%s: %s"), *PropertyNameAsString, *PropertyValueAsString);
			}
		}

		return ReturnValue;
	}

	UFUNCTION(BlueprintCallable, Category = "DeadlineService")
	static TMap<FString, FString> GetDeadlinePluginInfo(const FDeadlineJobPresetStruct& JobPresetStruct)
	{
		return JobPresetStruct.PluginInfo;
	}
};
